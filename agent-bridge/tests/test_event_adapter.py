import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_bridge.event_adapter import openhands_line_to_event


def test_openhands_action_line_maps_to_progress():
    line = '{"observation": null, "action": "run", "args": {"command": "npm run build"}}'
    e = openhands_line_to_event(line, job_id="j1", task_id="t1", nickname="dev", seq=2)
    assert e["kind"] == "progress"
    assert e["seq"] == 2
    assert e["payload"]["action"] == "run"


def test_openhands_finish_line_maps_to_succeeded():
    line = '{"action": "finish", "args": {"outputs": {"result": "done"}}}'
    e = openhands_line_to_event(line, job_id="j1", task_id="t1", nickname="dev", seq=9)
    assert e["kind"] == "succeeded"


def test_malformed_line_maps_to_progress_raw():
    e = openhands_line_to_event("not json", job_id="j1", task_id="t1", nickname="dev", seq=1)
    assert e["kind"] == "progress"
    assert e["payload"]["raw"] == "not json"
