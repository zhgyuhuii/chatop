import asyncio
import sys

import pytest

from station.events import EventHub
from station.tasks.dispatcher import Dispatcher
from station.tasks.store import TaskStore

FAKE_OK = [sys.executable, "-c", (
    "import json;"
    "print(json.dumps({'type':'assistant','message':{'content':[{'type':'text','text':'step1'}]}}));"
    "print(json.dumps({'type':'result','subtype':'success','is_error':False,'result':'done',"
    "'usage':{'input_tokens':7,'output_tokens':3}}))")]
FAKE_FAIL = [sys.executable, "-c", "import sys; sys.exit(2)"]


async def _wait_terminal(store, jid, timeout=5.0):
    for _ in range(int(timeout / 0.05)):
        if store.get_job(jid)["state"] in {"succeeded", "failed", "cancelled"}:
            return store.get_job(jid)
        await asyncio.sleep(0.05)
    raise TimeoutError


async def test_dispatch_success_flow(tmp_path):
    store, hub = TaskStore(tmp_path / "t.db"), EventHub()
    q = hub.subscribe()
    d = Dispatcher(store, hub, commands={"claude-code": lambda goal: FAKE_OK})
    jid = await d.dispatch("claude-code", "do it", str(tmp_path))
    job = await _wait_terminal(store, jid)
    assert job["state"] == "succeeded" and job["tokens"] == 10
    assert job["current_step"] == "step1"
    kinds = [q.get_nowait()["kind"] for _ in range(q.qsize())]
    assert "succeeded" in kinds
    assert store.list_events(jid)


async def test_dispatch_nonzero_exit_without_result_is_failed(tmp_path):
    store, hub = TaskStore(tmp_path / "t.db"), EventHub()
    d = Dispatcher(store, hub, commands={"codex": lambda goal: FAKE_FAIL})
    jid = await d.dispatch("codex", "boom", None)
    assert (await _wait_terminal(store, jid))["state"] == "failed"


async def test_dispatch_unknown_agent_raises(tmp_path):
    d = Dispatcher(TaskStore(tmp_path / "t.db"), EventHub(), commands={})
    with pytest.raises(KeyError):
        await d.dispatch("nope", "g", None)
