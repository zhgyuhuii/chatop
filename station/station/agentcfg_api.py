from __future__ import annotations

"""智能体统一配置中心 —— station 薄壳路由。

只做协议适配（参数校验、身份、事件桥接），业务全在 agent-config 引擎库。
引擎缺失时（未随镜像部署）路由降级为 503，不影响大屏其它功能。

长任务（扫码/配对）在线程里跑，事件经 loop.call_soon_threadsafe 桥接到 EventHub → SSE。
"""

import asyncio
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .events import EventHub

# 引擎防御式导入：缺失时 _ENGINE_ERR 记原因，路由统一 503。
_ENGINE_ERR: Optional[str] = None
try:
    from agentconfig.core import registry as _registry
    from agentconfig.models import providers as _providers
    from agentconfig.tutorials import loader as _tutorials
    from agentconfig.assistant import planner as _planner
    from agentconfig.assistant.llm import from_openclaw_config as _llm_from_cfg
except Exception as e:  # pragma: no cover - 仅缺依赖时触发
    _ENGINE_ERR = str(e)
    _registry = _providers = _tutorials = _planner = _llm_from_cfg = None


class ApplyReq(BaseModel):
    patch: dict


class ModelsReq(BaseModel):
    provider: str
    api_key: str = ""
    base_url: Optional[str] = None


class AuthStartReq(BaseModel):
    channel: str
    inputs: dict = {}


class AssistantReq(BaseModel):
    message: str
    agent: str = "openclaw"
    use_llm: bool = True


def _require_engine() -> None:
    if _ENGINE_ERR is not None:
        raise HTTPException(503, f"配置引擎不可用：{_ENGINE_ERR}")


def _adapter(agent_id: str):
    _require_engine()
    try:
        return _registry.get(agent_id)
    except KeyError:
        raise HTTPException(404, f"未知智能体 {agent_id}")


def register_agentcfg_routes(app: FastAPI, hub: EventHub,
                             home: Optional[Path] = None) -> None:
    """把配置中心路由挂到 station app。create_app 调用。"""
    if _registry is not None:
        _registry.install_defaults(home=str(home) if home else None)

    P = "/dashboard/api/agent-config"

    @app.get(P + "/agents")
    def cfg_agents() -> list[dict]:
        _require_engine()
        out = []
        for aid in _registry.ids():
            try:
                out.append(_registry.get(aid).status().to_dict())
            except Exception as e:
                out.append({"id": aid, "label": aid, "error": str(e)})
        return out

    @app.get(P + "/{agent_id}/describe")
    def cfg_describe(agent_id: str) -> dict:
        return _adapter(agent_id).describe().to_dict()

    @app.get(P + "/{agent_id}/config")
    def cfg_config(agent_id: str) -> dict:
        return _adapter(agent_id).read_config(redact=True)

    @app.post(P + "/{agent_id}/apply")
    def cfg_apply(agent_id: str, req: ApplyReq) -> dict:
        return _adapter(agent_id).apply(req.patch).to_dict()

    @app.post(P + "/{agent_id}/models")
    def cfg_models(agent_id: str, req: ModelsReq) -> dict:
        _require_engine()
        return _providers.verify_and_list(req.provider, req.api_key, req.base_url)

    @app.get(P + "/{agent_id}/auth-flow")
    def cfg_auth_flow(agent_id: str, channel: str) -> dict:
        return _adapter(agent_id).auth_flow(channel).to_dict()

    @app.post(P + "/{agent_id}/auth-flow/start")
    async def cfg_auth_start(agent_id: str, req: AuthStartReq) -> dict:
        adapter = _adapter(agent_id)
        loop = asyncio.get_running_loop()

        def emit(event) -> None:
            ev = event.to_dict() if hasattr(event, "to_dict") else event
            ev.setdefault("ts", time.time())
            ev.setdefault("kind", "agent-config")
            loop.call_soon_threadsafe(hub.publish, ev)

        def run_flow_safe() -> None:
            # run_flow 在线程里跑；异常必须显式 emit 成事件，否则 create_task 的未 await
            # 任务会把异常吞成 "Task exception was never retrieved"，前端永远等不到二维码。
            try:
                adapter.run_flow(req.channel, req.inputs, emit)
            except Exception as e:  # noqa: BLE001 - 任何失败都要让前端看到
                emit({"type": "flow:error", "channel": req.channel, "reason": str(e)})

        # 阻塞式 run_flow 丢到线程，事件线程安全地回灌 hub。
        asyncio.get_running_loop().create_task(asyncio.to_thread(run_flow_safe))
        return {"ok": True, "channel": req.channel, "streaming": True}

    @app.get(P + "/{agent_id}/tutorial")
    def cfg_tutorial(agent_id: str, channel: str) -> dict:
        _require_engine()
        auth = None
        try:
            auth = _adapter(agent_id).auth_flow(channel).kind
        except Exception:
            pass
        return _tutorials.get(agent_id, channel, auth)

    @app.post(P + "/{agent_id}/health")
    def cfg_health(agent_id: str) -> list[dict]:
        return [d.to_dict() for d in _adapter(agent_id).health_check()]

    @app.post(P + "/assistant")
    def cfg_assistant(req: AssistantReq) -> dict:
        _require_engine()
        llm = None
        if req.use_llm:
            try:
                oc = _registry.get("openclaw").read_config(redact=False)
                llm = _llm_from_cfg(oc if "_load_error" not in oc else {})
            except Exception:
                llm = None
        return _planner.respond(req.message, agent=req.agent, llm=llm)
