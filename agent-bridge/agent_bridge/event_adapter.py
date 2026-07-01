from __future__ import annotations

import json
from typing import Any

# Map OpenHands JSONL event stream (or claude stream-json) → unified Event dict (§6.6, B2).
_TERMINAL_ACTIONS = {"finish": "succeeded", "error": "failed"}


def openhands_line_to_event(line: str, job_id: str, task_id: str, nickname: str, seq: int) -> dict[str, Any]:
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return {"job_id": job_id, "task_id": task_id, "container": nickname,
                "kind": "progress", "seq": seq, "payload": {"raw": line}}

    action = obj.get("action")
    kind = _TERMINAL_ACTIONS.get(action, "progress")
    payload: dict[str, Any] = {"action": action} if action else {}
    payload.update({k: v for k, v in obj.items() if k != "action"})
    return {"job_id": job_id, "task_id": task_id, "container": nickname,
            "kind": kind, "seq": seq, "payload": payload}
