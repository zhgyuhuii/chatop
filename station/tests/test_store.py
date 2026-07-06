import pytest

from station.tasks.store import TaskStore


def _store(tmp_path):
    return TaskStore(tmp_path / "t.db")


def test_create_and_get(tmp_path):
    s = _store(tmp_path)
    job = s.create_job("claude-code", "fix bug", "/tmp/w")
    got = s.get_job(job["id"])
    assert got["agent"] == "claude-code" and got["state"] == "queued"
    assert got["source"] == "manual"


def test_legal_transition_chain(tmp_path):
    s = _store(tmp_path)
    j = s.create_job("codex", "g", None)
    s.transition(j["id"], "running")
    s.transition(j["id"], "succeeded")
    assert s.get_job(j["id"])["state"] == "succeeded"


def test_illegal_transition_raises(tmp_path):
    s = _store(tmp_path)
    j = s.create_job("codex", "g", None)
    with pytest.raises(ValueError):
        s.transition(j["id"], "succeeded")  # queued 不能直达终态


def test_step_tokens_and_events(tmp_path):
    s = _store(tmp_path)
    j = s.create_job("codex", "g", None)
    s.set_step(j["id"], "editing auth.js")
    s.add_tokens(j["id"], 120)
    s.append_event({"job_id": j["id"], "seq": 0, "kind": "progress", "payload": {"a": 1}, "ts": 1.0})
    got = s.get_job(j["id"])
    assert got["current_step"] == "editing auth.js" and got["tokens"] == 120
    assert s.list_events(j["id"])[0]["payload"] == {"a": 1}


def test_upsert_detected_idempotent(tmp_path):
    s = _store(tmp_path)
    s.upsert_detected("detected-claude-abc", "claude-code", "sess-1", "running")
    s.upsert_detected("detected-claude-abc", "claude-code", "sess-1", "succeeded")
    jobs = s.list_jobs()
    assert len(jobs) == 1 and jobs[0]["state"] == "succeeded" and jobs[0]["source"] == "detected"
