from __future__ import annotations

import json
import re
import time
from pathlib import Path

# type: runtime=常驻进程 | session=会话式 CLI | human=人工桌面型
AGENT_SPECS: dict[str, dict] = {
    "claude-code": {"type": "session", "proc_match": "claude",
                    "config_candidates": [".claude.json", ".claude/settings.json"],
                    "session_glob": ".claude/projects/*/*.jsonl"},
    "codex": {"type": "session", "proc_match": "codex",
              "config_candidates": [".codex/auth.json", ".codex/config.toml"],
              "session_glob": ".codex/sessions/**/*.jsonl"},
    "openclaw": {"type": "runtime", "proc_match": "openclaw",
                 "config_candidates": [".openclaw/openclaw.json", ".config/openclaw/config.json"],
                 "session_glob": None},
    "hermes": {"type": "runtime", "proc_match": "hermes",
               "config_candidates": [".hermes/config.yaml", ".hermes/config.json", ".hermes/.env"],
               "session_glob": None},
    "openhuman": {"type": "human", "proc_match": "openhuman",
                  "config_candidates": ["Applications/openhuman/squashfs-root"],
                  "session_glob": None},
}
_FRESH_S = 900  # 15min 内活动的会话算 active


def _read_model(path: Path) -> str:
    try:
        text = path.read_text()
    except OSError:
        return ""
    if path.suffix == ".json":
        try:
            return str(json.loads(text).get("model", ""))
        except ValueError:
            return ""
    m = re.search(r'^\s*model\s*=\s*"([^"]+)"', text, re.M)  # toml
    return m.group(1) if m else ""


def probe_agent(agent_id: str, spec: dict, home: Path, procs: list[dict],
                now: float | None = None) -> dict:
    now = now or time.time()
    configured, model = False, ""
    for rel in spec["config_candidates"]:
        p = home / rel
        if p.is_dir() or (p.is_file() and p.stat().st_size > 0):
            configured = True
            if p.is_file():
                model = model or _read_model(p)
    matched = [p for p in procs if spec["proc_match"] in (p.get("name", "") + " " + p.get("cmdline", ""))]
    active, last = 0, 0.0
    if spec.get("session_glob"):
        for f in home.glob(spec["session_glob"]):
            try:
                mt = f.stat().st_mtime
            except OSError:
                continue
            last = max(last, mt)
            if now - mt < _FRESH_S:
                active += 1
    return {"id": agent_id, "agent_type": spec["type"], "configured": configured, "model": model,
            "running": bool(matched), "active_sessions": active, "last_active": last,
            "cpu": round(sum(p.get("cpu", 0.0) for p in matched), 1),
            "mem_mb": round(sum(p.get("mem_mb", 0.0) for p in matched), 1)}
