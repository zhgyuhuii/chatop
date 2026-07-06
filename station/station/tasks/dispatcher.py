from __future__ import annotations

import asyncio
import time
from typing import Callable

from ..events import EventHub
from .event_adapter import PARSERS, claude_line_to_event
from .store import TERMINAL, TaskStore

# 无头派活命令表。容器即工位（单用户已隔离），跳过交互确认是有意为之。
AGENT_COMMANDS: dict[str, Callable[[str], list[str]]] = {
    "claude-code": lambda goal: ["claude", "-p", goal, "--output-format", "stream-json",
                                 "--verbose", "--dangerously-skip-permissions"],
    "codex": lambda goal: ["codex", "exec", "--full-auto", "--json", goal],
}


class Dispatcher:
    def __init__(self, store: TaskStore, hub: EventHub, nickname: str = "workstation",
                 commands: dict | None = None, parsers: dict | None = None) -> None:
        self._store, self._hub, self._nick = store, hub, nickname
        self._commands = AGENT_COMMANDS if commands is None else commands
        self._parsers = PARSERS if parsers is None else parsers

    @property
    def dispatchable(self) -> set[str]:
        return set(self._commands)

    async def dispatch(self, agent: str, goal: str, workdir: str | None) -> str:
        if agent not in self._commands:
            raise KeyError(f"agent {agent} not dispatchable")
        job = self._store.create_job(agent, goal, workdir)
        asyncio.get_running_loop().create_task(self._run(job))
        return job["id"]

    def _emit(self, ev: dict) -> None:
        self._store.append_event(ev)
        self._hub.publish(ev)

    async def _run(self, job: dict) -> None:
        jid, agent = job["id"], job["agent"]
        parse = self._parsers.get(agent, claude_line_to_event)
        self._store.transition(jid, "running")
        self._emit({"job_id": jid, "container": self._nick, "kind": "progress",
                    "seq": 0, "payload": {"text": "started", "agent": agent}, "ts": time.time()})
        try:
            proc = await asyncio.create_subprocess_exec(
                *self._commands[agent](job["goal"]), cwd=job["workdir"] or None,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        except OSError as e:
            self._store.transition(jid, "failed")
            self._emit({"job_id": jid, "container": self._nick, "kind": "failed",
                        "seq": 1, "payload": {"message": f"spawn failed: {e}"}, "ts": time.time()})
            return
        seq, final = 1, None
        assert proc.stdout is not None
        while True:
            raw = await proc.stdout.readline()
            if not raw:
                break
            ev = parse(raw.decode(errors="replace").rstrip("\n"), jid, self._nick, seq)
            seq += 1
            self._emit(ev)
            p = ev.get("payload", {})
            if p.get("text"):
                self._store.set_step(jid, p["text"])
            if p.get("tokens"):
                self._store.add_tokens(jid, int(p["tokens"]))
            if ev["kind"] in TERMINAL:
                final = ev["kind"]
        rc = await proc.wait()
        state = final or ("succeeded" if rc == 0 else "failed")
        if self._store.get_job(jid)["state"] not in TERMINAL:
            self._store.transition(jid, state)
        if final is None:
            self._emit({"job_id": jid, "container": self._nick, "kind": state,
                        "seq": seq, "payload": {"exit_code": rc}, "ts": time.time()})
