# -*- coding: utf-8 -*-
import pytest

from agentconfig.core import registry
from agentconfig.assistant import planner
from agentconfig.assistant.llm import FakeLLMClient
from conftest import build_catalog_snapshot


@pytest.fixture(autouse=True)
def _reg(tmp_path):
    build_catalog_snapshot(str(tmp_path))
    registry.install_defaults(home=str(tmp_path))
    registry.reset()
    yield


def test_intent_channel_wecom_not_wechat():
    r = planner.route_intent("帮我接入企业微信")
    assert r["kind"] == "channel_setup" and r["channel"] == "wecom"


def test_intent_wechat_personal():
    r = planner.route_intent("连接微信")
    assert r["channel"] == "openclaw-weixin"


def test_intent_model_provider():
    r = planner.route_intent("配 deepseek 模型")
    assert r["kind"] == "model_setup" and r["provider"] == "deepseek"


def test_respond_no_llm_degrades_to_intent():
    r = planner.respond("接入 telegram", llm=None)
    assert r["mode"] == "intent" and r["channel"] == "telegram"


def test_respond_no_llm_fallback():
    r = planner.respond("今天天气怎么样", llm=None)
    assert r["kind"] == "fallback"


def test_llm_tool_loop_executes_tool():
    fake = FakeLLMClient([
        {"content": "", "tool_calls": [
            {"id": "1", "function": {"name": "get_tutorial",
                                     "arguments": '{"channel":"wecom"}'}}]},
        {"content": "企业微信要填 CorpID/Secret。", "tool_calls": []},
    ])
    r = planner.respond("怎么接入企业微信", llm=fake)
    assert r["mode"] == "llm"
    assert [t["name"] for t in r["tools_used"]] == ["get_tutorial"]
    assert "企业微信" in r["reply"]


def test_llm_unavailable_degrades():
    class Boom:
        def chat(self, messages, tools=None):
            from agentconfig.assistant.llm import LLMUnavailable
            raise LLMUnavailable("down")
    r = planner.respond("接入企业微信", llm=Boom())
    assert r["mode"] == "intent_degraded" and r.get("channel") == "wecom"


def test_provider_alias_has_no_ghost_qwen():
    from agentconfig.assistant import planner
    vals = set(planner._PROVIDER_ALIASES.values())
    assert "qwen" not in vals
