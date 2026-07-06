import json

from station.tasks.event_adapter import PARSERS, claude_line_to_event, codex_line_to_event


def test_claude_result_success_maps_succeeded_with_tokens():
    line = json.dumps({"type": "result", "subtype": "success", "is_error": False,
                       "result": "done", "usage": {"input_tokens": 10, "output_tokens": 5}})
    ev = claude_line_to_event(line, "j1", "ws", 3)
    assert ev["kind"] == "succeeded" and ev["seq"] == 3 and ev["job_id"] == "j1"
    assert ev["payload"]["tokens"] == 15


def test_claude_error_result_maps_failed():
    line = json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True})
    assert claude_line_to_event(line, "j", "ws", 0)["kind"] == "failed"


def test_claude_assistant_maps_progress_with_text():
    line = json.dumps({"type": "assistant",
                       "message": {"content": [{"type": "text", "text": "editing file"}]}})
    ev = claude_line_to_event(line, "j", "ws", 1)
    assert ev["kind"] == "progress" and ev["payload"]["text"] == "editing file"


def test_codex_task_complete_maps_succeeded():
    line = json.dumps({"id": "0", "msg": {"type": "task_complete"}})
    assert codex_line_to_event(line, "j", "ws", 0)["kind"] == "succeeded"


def test_codex_error_maps_failed():
    line = json.dumps({"msg": {"type": "error", "message": "boom"}})
    assert codex_line_to_event(line, "j", "ws", 0)["kind"] == "failed"


def test_garbage_line_is_progress_raw():
    ev = claude_line_to_event("not json", "j", "ws", 0)
    assert ev["kind"] == "progress" and ev["payload"]["raw"] == "not json"


def test_parsers_registry():
    assert set(PARSERS) >= {"claude-code", "codex"}
