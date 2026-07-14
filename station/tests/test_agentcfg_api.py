"""配置中心薄壳路由测试。引擎已随 PYTHONPATH（agent-config）可导入。

用 TestClient 打通各端点，验证薄壳把请求正确转给引擎且响应形状对。
"""
import json
import os
import sys

import httpx
import pytest

from station.api import create_app
from station.events import EventHub
from station.tasks.dispatcher import Dispatcher
from station.tasks.store import TaskStore

# 引擎复用 openclaw-tool 纯模块；测试指到仓内。
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("OPENCLAW_TOOL_DIR", os.path.join(_REPO, "chatop/openclaw-tool")
                      if os.path.isdir(os.path.join(_REPO, "chatop/openclaw-tool"))
                      else os.path.join(_REPO, "openclaw-tool"))

pytest.importorskip("agentconfig", reason="agent-config 引擎需在 PYTHONPATH")


def _build_snapshot(home):
    sys.path.insert(0, os.environ["OPENCLAW_TOOL_DIR"])
    import openclaw_catalog as cat
    td = os.path.join(os.environ["OPENCLAW_TOOL_DIR"], "testdata")
    catalog = cat.build_catalog(
        open(os.path.join(td, "channels-list.json"), encoding="utf-8").read(),
        open(os.path.join(td, "config-schema-channels.json"), encoding="utf-8").read(),
        open(os.path.join(td, "plugin-catalog-snippet.js"), encoding="utf-8").read(),
        open(os.path.join(td, "models-list.json"), encoding="utf-8").read(),
        openclaw_version="2026.6.10")
    cat.save_catalog(os.path.join(home, ".cache/chatop/openclaw-catalog.json"), catalog)


def _app(tmp_path):
    _build_snapshot(str(tmp_path))
    store, hub = TaskStore(tmp_path / "t.db"), EventHub()
    disp = Dispatcher(store, hub, commands={})
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"apps": []}))
    # 引擎注册表是进程级单例，重置以绑定本测试 home
    from agentconfig.core import registry
    registry.reset()
    app = create_app(store, hub, disp, home=tmp_path, catalog_path=catalog)
    registry.install_defaults(home=str(tmp_path))
    registry.reset()
    return app


def _client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


P = "/dashboard/api/agent-config"


async def test_agents_overview(tmp_path):
    app = _app(tmp_path)
    async with _client(app) as c:
        r = await c.get(P + "/agents")
        assert r.status_code == 200
        ids = {a["id"] for a in r.json()}
        assert {"openclaw", "hermes"} <= ids


async def test_describe(tmp_path):
    app = _app(tmp_path)
    async with _client(app) as c:
        r = await c.get(P + "/openclaw/describe")
        assert r.status_code == 200
        gids = {g["id"] for g in r.json()["groups"]}
        assert "channels" in gids


async def test_auth_flow(tmp_path):
    app = _app(tmp_path)
    async with _client(app) as c:
        r = await c.get(P + "/openclaw/auth-flow", params={"channel": "openclaw-weixin"})
        assert r.json()["kind"] == "qr"
        # wecom 的 openclaw schema 为空壳（无字段）→ 走 free_kv 自由键值编辑器
        r2 = await c.get(P + "/openclaw/auth-flow", params={"channel": "wecom"})
        assert r2.json()["kind"] == "token" and r2.json()["free_kv"] is True
        # telegram 有真实 schema 字段（botToken 等）→ fields 非空
        r3 = await c.get(P + "/openclaw/auth-flow", params={"channel": "telegram"})
        assert r3.json()["fields"] and any(
            f["key"] == "channels.telegram.botToken" for f in r3.json()["fields"])


async def test_models_endpoint_falls_back(tmp_path):
    app = _app(tmp_path)
    async with _client(app) as c:
        # 无 key → 回退快照（不发真网）
        r = await c.post(P + "/openclaw/models", json={"provider": "deepseek"})
        assert r.status_code == 200
        assert r.json()["source"] == "snapshot"


async def test_apply_and_config(tmp_path):
    app = _app(tmp_path)
    async with _client(app) as c:
        r = await c.post(P + "/openclaw/apply", json={
            "patch": {"agents": {"defaults": {"model": {"primary": "deepseek/deepseek-chat"}}}}})
        assert r.json()["ok"]
        r2 = await c.get(P + "/openclaw/config")
        assert r2.json()["agents"]["defaults"]["model"]["primary"] == "deepseek/deepseek-chat"


async def test_tutorial_endpoint(tmp_path):
    app = _app(tmp_path)
    async with _client(app) as c:
        r = await c.get(P + "/openclaw/tutorial", params={"channel": "wecom"})
        assert r.json()["steps"] and r.json()["auth"] == "token"


async def test_assistant_intent_without_llm(tmp_path):
    app = _app(tmp_path)
    async with _client(app) as c:
        r = await c.post(P + "/assistant", json={"message": "接入企业微信", "use_llm": False})
        assert r.json()["channel"] == "wecom"


async def test_unknown_agent_404(tmp_path):
    app = _app(tmp_path)
    async with _client(app) as c:
        r = await c.get(P + "/nope/describe")
        assert r.status_code == 404


async def test_health_endpoint(tmp_path):
    app = _app(tmp_path)
    async with _client(app) as c:
        r = await c.post(P + "/openclaw/health")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


async def test_providers_endpoint(tmp_path):
    app = _app(tmp_path)
    async with _client(app) as c:
        r = await c.get(P + "/openclaw/providers")
        assert r.status_code == 200
        ids = {p["id"] for p in r.json()["providers"]}
        assert {"deepseek", "github-copilot"} <= ids
        dv = next(p for p in r.json()["providers"] if p["id"] == "deepseek")
        assert dv["has_live"] is True and dv["auth_kind"] == "key"
