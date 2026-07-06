import json
import os
import time

from station.tasks.session_watch import scan_sessions
from station.tasks.store import TaskStore


def _mk(home, rel, lines, age_s):
    f = home / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("\n".join(lines))
    t = time.time() - age_s
    os.utime(f, (t, t))
    return f


def test_fresh_session_becomes_running_task(tmp_path):
    _mk(tmp_path, ".claude/projects/p/s1.jsonl", ["{}"], age_s=10)
    store = TaskStore(tmp_path / "t.db")
    scan_sessions(tmp_path, store)
    jobs = store.list_jobs()
    assert len(jobs) == 1 and jobs[0]["state"] == "running" and jobs[0]["source"] == "detected"


def test_stale_session_with_success_result_is_succeeded(tmp_path):
    line = json.dumps({"type": "result", "subtype": "success", "is_error": False})
    _mk(tmp_path, ".claude/projects/p/s2.jsonl", ["{}", line], age_s=3600)
    store = TaskStore(tmp_path / "t.db")
    scan_sessions(tmp_path, store)
    assert store.list_jobs()[0]["state"] == "succeeded"


def test_stale_unparseable_session_is_skipped(tmp_path):
    _mk(tmp_path, ".claude/projects/p/s3.jsonl", ["garbage"], age_s=3600)
    store = TaskStore(tmp_path / "t.db")
    scan_sessions(tmp_path, store)
    assert store.list_jobs() == []


def test_scan_is_idempotent(tmp_path):
    _mk(tmp_path, ".claude/projects/p/s1.jsonl", ["{}"], age_s=10)
    store = TaskStore(tmp_path / "t.db")
    scan_sessions(tmp_path, store)
    scan_sessions(tmp_path, store)
    assert len(store.list_jobs()) == 1
