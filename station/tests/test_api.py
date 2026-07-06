import asyncio
import json
import sys

import httpx

from station.api import create_app
from station.events import EventHub
from station.tasks.dispatcher import Dispatcher
from station.tasks.store import TaskStore

FAKE_OK = [sys.executable, "-c",
           "import json; print(json.dumps({'type':'result','subtype':'success','is_error':False}))"]


def _app(tmp_path, spawned=None, posted=None):
    store, hub = TaskStore(tmp_path / "t.db"), EventHub()
    disp = Dispatcher(store, hub, commands={"claude-code": lambda g: FAKE_OK})
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"apps": [
        {"id": "claude-code", "name": "Claude Code", "category": "ai-cli", "detect": "true"},
        {"id": "hermes", "name": "Hermes", "category": "ai-runtime", "detect": "false"}]}))
    app = create_app(store, hub, disp, home=tmp_path, catalog_path=catalog,
                     action_spawn=(spawned.append if spawned is not None else None),
                     action_post=((lambda p, b: posted.append((p, b)) or {}) if posted is not None else None))
    return app, store, hub


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def test_agents_endpoint(tmp_path):
    app, *_ = _app(tmp_path)
    async with _client(app) as c:
        r = await c.get("/dashboard/api/agents")
    assert r.status_code == 200
    agents = {a["id"]: a for a in r.json()}
    assert agents["claude-code"]["installed"] and "configured" in agents["claude-code"]
    assert agents["hermes"]["installed"] is False  # 未装的也上屏（带安装入口）


async def test_dispatch_and_tasks(tmp_path):
    app, store, _ = _app(tmp_path)
    async with _client(app) as c:
        r = await c.post("/dashboard/api/dispatch", json={"agent": "claude-code", "goal": "hi"})
        assert r.status_code == 200
        jid = r.json()["job_id"]
        for _ in range(50):
            if store.get_job(jid)["state"] == "succeeded":
                break
            await asyncio.sleep(0.05)
        r2 = await c.get("/dashboard/api/tasks")
        assert any(t["id"] == jid for t in r2.json())
        r3 = await c.get(f"/dashboard/api/tasks/{jid}/events")
        assert r3.status_code == 200 and isinstance(r3.json(), list)


async def test_dispatch_unknown_agent_400(tmp_path):
    app, *_ = _app(tmp_path)
    async with _client(app) as c:
        r = await c.post("/dashboard/api/dispatch", json={"agent": "nope", "goal": "g"})
    assert r.status_code == 400


async def test_system_endpoint(tmp_path):
    app, *_ = _app(tmp_path)
    async with _client(app) as c:
        r = await c.get("/dashboard/api/system")
    snap = r.json()
    assert "cpu" in snap and "services" in snap


async def test_agent_open_and_install_actions(tmp_path):
    spawned, posted = [], []
    app, *_ = _app(tmp_path, spawned=spawned, posted=posted)
    async with _client(app) as c:
        r1 = await c.post("/dashboard/api/agents/claude-code/open")
        r2 = await c.post("/dashboard/api/agents/hermes/install")
        r3 = await c.post("/dashboard/api/agents/nope/open")
    assert r1.status_code == 200 and spawned == [["chatop-run-cli", "claude"]]
    assert r2.status_code == 200 and posted == [("/apps/install", {"id": "hermes"})]
    assert r3.status_code == 400


async def test_agent_configure_action(tmp_path):
    spawned = []
    app, *_ = _app(tmp_path, spawned=spawned, posted=[])
    async with _client(app) as c:
        r = await c.post("/dashboard/api/agents/hermes/configure")
    assert r.status_code == 200 and spawned == [["chatop-run-cli", "hermes", "setup"]]


async def test_sse_stream_delivers_published_event():
    from station.api import stream_events
    from station.events import EventHub

    hub = EventHub()
    gen = stream_events(hub)

    async def flow():
        first = await gen.__anext__()  # 订阅发生在生成器启动时
        assert "connected" in first
        hub.publish({"kind": "progress", "seq": 1, "job_id": "j"})
        chunk = await gen.__anext__()
        assert '"seq": 1' in chunk

    await asyncio.wait_for(flow(), timeout=10)
    await gen.aclose()
