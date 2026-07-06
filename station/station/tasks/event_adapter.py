from __future__ import annotations

import json
import time
from typing import Any

# 统一事件 schema 对齐 ChaCMD：job_id/container/kind/seq/payload/ts。
# kind: progress | succeeded | failed


def _base(job_id: str, nickname: str, seq: int, kind: str, payload: dict) -> dict[str, Any]:
    return {"job_id": job_id, "container": nickname, "kind": kind,
            "seq": seq, "payload": payload, "ts": time.time()}


def _loads(line: str) -> dict | None:
    try:
        obj = json.loads(line)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def claude_line_to_event(line: str, job_id: str, nickname: str, seq: int) -> dict:
    """claude -p --output-format stream-json --verbose 的 JSONL。"""
    obj = _loads(line)
    if obj is None:
        return _base(job_id, nickname, seq, "progress", {"raw": line})
    t = obj.get("type")
    if t == "result":
        ok = not obj.get("is_error") and obj.get("subtype") == "success"
        usage = obj.get("usage") or {}
        tokens = int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
        payload = {"result": obj.get("result", ""), "tokens": tokens}
        return _base(job_id, nickname, seq, "succeeded" if ok else "failed", payload)
    if t == "assistant":
        content = (obj.get("message") or {}).get("content") or []
        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        return _base(job_id, nickname, seq, "progress", {"text": " ".join(texts)[:500]})
    return _base(job_id, nickname, seq, "progress", {"type": t})


def codex_line_to_event(line: str, job_id: str, nickname: str, seq: int) -> dict:
    """codex exec --json 的 JSONL（{"msg":{"type":...}}）。"""
    obj = _loads(line)
    if obj is None:
        return _base(job_id, nickname, seq, "progress", {"raw": line})
    msg = obj.get("msg") or {}
    t = msg.get("type", "")
    if t == "task_complete":
        return _base(job_id, nickname, seq, "succeeded", {k: v for k, v in msg.items() if k != "type"})
    if t == "error":
        return _base(job_id, nickname, seq, "failed", {"message": msg.get("message", "")})
    return _base(job_id, nickname, seq, "progress", {"type": t, "text": str(msg.get("message", ""))[:500]})


def openhands_line_to_event(line: str, job_id: str, nickname: str, seq: int) -> dict:
    """OpenHands JSONL（保留 agent-bridge 原映射，供将来常驻 runtime 用）。"""
    obj = _loads(line)
    if obj is None:
        return _base(job_id, nickname, seq, "progress", {"raw": line})
    action = obj.get("action")
    kind = {"finish": "succeeded", "error": "failed"}.get(action, "progress")
    payload: dict[str, Any] = {"action": action} if action else {}
    payload.update({k: v for k, v in obj.items() if k != "action"})
    return _base(job_id, nickname, seq, kind, payload)


PARSERS = {"claude-code": claude_line_to_event, "codex": codex_line_to_event,
           "openhands": openhands_line_to_event}
