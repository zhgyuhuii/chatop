from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from typing import Callable

APP_MANAGER = "http://127.0.0.1:8686"

# 打开智能体：会话式/常驻 CLI → 桌面终端（chatop-run-cli）；GUI 型 → app-manager /apps/launch
OPEN_COMMANDS: dict[str, list[str] | None] = {
    "claude-code": ["chatop-run-cli", "claude"],
    "codex": ["chatop-run-cli", "codex"],
    "openclaw": ["chatop-run-cli", "openclaw", "gateway"],
    "hermes": ["chatop-run-cli", "hermes"],
    "openhuman": None,
}

# 打开配置界面：openclaw → openclaw-tool 可视化配置器(tkinter)；hermes → hermes setup；
# claude/codex 配置在其 CLI 内；openhuman 配置在应用内
CONFIG_COMMANDS: dict[str, list[str] | None] = {
    "openclaw": ["python3", "/opt/openclaw-tool/openclaw_config_gui.py"],
    "hermes": ["chatop-run-cli", "hermes", "setup"],
    "claude-code": ["chatop-run-cli", "claude"],
    "codex": ["chatop-run-cli", "codex", "login"],
    "openhuman": None,
}


def _spawn(cmd: list[str]) -> None:
    env = dict(os.environ)
    env["DISPLAY"] = env.get("DISPLAY", ":1") or ":1"
    subprocess.Popen(cmd, env=env, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(APP_MANAGER + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 固定回环地址
        return json.loads(resp.read() or b"{}")


def _run(table: dict, agent_id: str, spawn: Callable, post: Callable) -> dict:
    if agent_id not in table:
        raise KeyError(f"no action for agent {agent_id}")
    cmd = table[agent_id]
    if cmd is None:
        post("/apps/launch", {"id": agent_id})
    else:
        spawn(cmd)
    return {"ok": True, "agent": agent_id}


def open_agent(agent_id: str, spawn: Callable = _spawn, post: Callable = _post) -> dict:
    return _run(OPEN_COMMANDS, agent_id, spawn, post)


def configure_agent(agent_id: str, spawn: Callable = _spawn, post: Callable = _post) -> dict:
    return _run(CONFIG_COMMANDS, agent_id, spawn, post)


def install_agent(agent_id: str, post: Callable = _post) -> dict:
    post("/apps/install", {"id": agent_id})
    return {"ok": True, "agent": agent_id, "state": "queued"}
