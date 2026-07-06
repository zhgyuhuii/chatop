from __future__ import annotations

import hashlib
import time
from pathlib import Path

from ..probe.agent_probes import AGENT_SPECS
from .event_adapter import PARSERS
from .store import TaskStore

_FRESH_S = 180      # 3min 内有写入 → 认为会话进行中
_MAX_AGE_S = 86400  # 只看 24h 内的会话


def scan_sessions(home: Path, store: TaskStore, now: float | None = None) -> None:
    now = now or time.time()
    for agent_id, spec in AGENT_SPECS.items():
        glob = spec.get("session_glob")
        if not glob:
            continue
        parse = PARSERS.get(agent_id)
        for f in home.glob(glob):
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            age = now - mtime
            if age > _MAX_AGE_S:
                continue
            jid = f"detected-{agent_id}-{hashlib.sha1(str(f).encode()).hexdigest()[:12]}"
            if age < _FRESH_S:
                store.upsert_detected(jid, agent_id, f.stem, "running")
                continue
            state = None
            if parse:
                try:
                    lines = f.read_text(errors="replace").strip().splitlines()
                except OSError:
                    continue
                if lines:
                    kind = parse(lines[-1], jid, "detected", 0)["kind"]
                    if kind in ("succeeded", "failed"):
                        state = kind
            if state:  # 结局不可判的陈旧会话不入库（诚实优先）
                store.upsert_detected(jid, agent_id, f.stem, state)
