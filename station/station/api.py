from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import actions, config
from .events import EventHub, sse_format
from .probe.agent_probes import AGENT_SPECS, probe_agent
from .probe.catalog import detect_installed, load_ai_apps
from .probe.system import list_procs, snapshot
from .tasks.dispatcher import Dispatcher
from .tasks.session_watch import scan_sessions
from .tasks.store import TaskStore


class DispatchReq(BaseModel):
    agent: str
    goal: str
    workdir: str | None = None


async def stream_events(hub: EventHub):
    """SSE 帧生成器（模块级，便于单测——ASGITransport 会缓冲无限流）。"""
    q = hub.subscribe()
    try:
        yield ": connected\n\n"
        while True:
            yield sse_format(await q.get())
    finally:
        hub.unsubscribe(q)


def create_app(store: TaskStore, hub: EventHub, dispatcher: Dispatcher,
               home: Path | None = None, catalog_path: Path | None = None,
               web_dir: Path | None = None,
               action_spawn: Callable | None = None,
               action_post: Callable | None = None) -> FastAPI:
    home = home or config.HOME
    catalog_path = catalog_path or config.CATALOG_PATH
    spawn = action_spawn or actions._spawn
    post = action_post or actions._post
    app = FastAPI(title="chatop station")

    @app.get("/dashboard/api/agents")
    def agents() -> list[dict]:
        procs = list_procs()
        out = []
        for a in detect_installed(load_ai_apps(catalog_path)):
            st = (probe_agent(a["id"], AGENT_SPECS[a["id"]], home, procs)
                  if a["installed"] and a["id"] in AGENT_SPECS else {})
            out.append({**a, **st, "dispatchable": a["id"] in dispatcher.dispatchable,
                        "openable": a["id"] in actions.OPEN_COMMANDS,
                        "configurable": a["id"] in actions.CONFIG_COMMANDS})
        return out

    @app.post("/dashboard/api/agents/{agent_id}/open")
    def agent_open(agent_id: str) -> dict:
        try:
            return actions.open_agent(agent_id, spawn=spawn, post=post)
        except KeyError as e:
            raise HTTPException(400, str(e))

    @app.post("/dashboard/api/agents/{agent_id}/configure")
    def agent_configure(agent_id: str) -> dict:
        try:
            return actions.configure_agent(agent_id, spawn=spawn, post=post)
        except KeyError as e:
            raise HTTPException(400, str(e))

    @app.post("/dashboard/api/agents/{agent_id}/install")
    def agent_install(agent_id: str) -> dict:
        try:
            return actions.install_agent(agent_id, post=post)
        except OSError as e:
            raise HTTPException(502, f"app-manager unreachable: {e}")

    @app.get("/dashboard/api/tasks")
    def tasks() -> list[dict]:
        scan_sessions(home, store)
        return store.list_jobs()

    @app.get("/dashboard/api/tasks/{job_id}/events")
    def task_events(job_id: str) -> list[dict]:
        try:
            store.get_job(job_id)
        except KeyError:
            raise HTTPException(404, "no such job")
        return store.list_events(job_id)

    @app.post("/dashboard/api/dispatch")
    async def dispatch(req: DispatchReq) -> dict:
        try:
            jid = await dispatcher.dispatch(req.agent, req.goal, req.workdir)
        except KeyError as e:
            raise HTTPException(400, str(e))
        return {"job_id": jid}

    @app.get("/dashboard/api/system")
    def system() -> dict:
        return snapshot()

    @app.get("/dashboard/api/events")
    async def events() -> StreamingResponse:
        return StreamingResponse(stream_events(hub), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    # 智能体统一配置中心路由（引擎缺失时内部降级为 503，不影响其它路由）。
    try:
        from .agentcfg_api import register_agentcfg_routes
        register_agentcfg_routes(app, hub, home=home)
    except Exception:  # pragma: no cover - 导入期异常也不应拖垮大屏
        pass

    wd = web_dir or config.web_dir()
    from .updater_api import create_router as _updater_router
    app.include_router(_updater_router())
    if wd.is_dir():  # 前端产物存在才挂（后端单测不需要）
        app.mount("/dashboard", StaticFiles(directory=str(wd), html=True), name="web")
    return app
