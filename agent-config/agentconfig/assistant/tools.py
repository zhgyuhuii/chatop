# -*- coding: utf-8 -*-
"""LLM 助手可调工具 —— 只操作引擎，不直接碰 UI。

每个工具是纯函数（除 apply/start_auth 有副作用），返回 JSON 可序列化结果。
工具的 OpenAI function schema 供 LLM 走「工具调用」循环；同一批工具也被确定性
意图路由（planner）直接调用，两条路径共用实现。
"""
from __future__ import annotations

from typing import Callable, Optional

from ..core import registry


def list_channels(agent: str = "openclaw") -> dict:
    """列出某智能体的通道及启用/认证状态。"""
    ad = registry.get(agent)
    desc = ad.describe()
    chans = []
    for g in desc.groups:
        for c in g.channels:
            chans.append({"id": c.id, "label": c.label, "auth": c.auth,
                          "enabled": c.enabled, "configured": c.configured,
                          "supports_qr": c.supports_qr})
    return {"agent": agent, "channels": chans}


def get_tutorial(channel: str, agent: str = "openclaw") -> dict:
    from ..tutorials import loader
    return loader.get(agent, channel)


def get_auth_flow(channel: str, agent: str = "openclaw") -> dict:
    ad = registry.get(agent)
    return ad.auth_flow(channel).to_dict()


def list_models(provider: str, api_key: str = "") -> dict:
    from ..models import providers
    return providers.verify_and_list(provider, api_key)


def set_field(agent: str, key: str, value, *, apply: bool = True) -> dict:
    """把 key（点路径，如 agents.defaults.model.primary）设为 value 并可选写盘。"""
    ad = registry.get(agent)
    patch = _dotted_to_nested(key, value)
    if not apply:
        return {"ok": True, "patch": patch, "applied": False}
    res = ad.apply(patch)
    return {"ok": res.ok, "applied": True, "removed": res.removed,
            "message": res.message}


def enable_channel(agent: str, channel: str, *, apply: bool = True) -> dict:
    return set_field(agent, f"channels.{channel}.enabled", True, apply=apply)


def _dotted_to_nested(dotted: str, value) -> dict:
    parts = dotted.split(".")
    out: dict = {}
    cur = out
    for p in parts[:-1]:
        cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value
    return out


# OpenAI function-calling schema。
SCHEMAS = [
    {"type": "function", "function": {
        "name": "list_channels", "description": "列出智能体的通道及状态",
        "parameters": {"type": "object", "properties": {
            "agent": {"type": "string", "enum": ["openclaw", "hermes"]}}, "required": []}}},
    {"type": "function", "function": {
        "name": "get_tutorial", "description": "获取某通道的图文设置教程",
        "parameters": {"type": "object", "properties": {
            "channel": {"type": "string"},
            "agent": {"type": "string"}}, "required": ["channel"]}}},
    {"type": "function", "function": {
        "name": "get_auth_flow", "description": "获取某通道启用后的认证流程（扫码/填Token/验证码等）",
        "parameters": {"type": "object", "properties": {
            "channel": {"type": "string"},
            "agent": {"type": "string"}}, "required": ["channel"]}}},
    {"type": "function", "function": {
        "name": "list_models", "description": "用 API Key 拉取某厂商可用模型清单",
        "parameters": {"type": "object", "properties": {
            "provider": {"type": "string"},
            "api_key": {"type": "string"}}, "required": ["provider"]}}},
    {"type": "function", "function": {
        "name": "enable_channel", "description": "启用某通道并写盘",
        "parameters": {"type": "object", "properties": {
            "agent": {"type": "string"},
            "channel": {"type": "string"}}, "required": ["agent", "channel"]}}},
    {"type": "function", "function": {
        "name": "set_field", "description": "设置某配置字段（点路径）并写盘",
        "parameters": {"type": "object", "properties": {
            "agent": {"type": "string"}, "key": {"type": "string"},
            "value": {}}, "required": ["agent", "key", "value"]}}},
]

# 名称 → 实现，供 planner 与 LLM 工具循环共用。
DISPATCH: dict[str, Callable] = {
    "list_channels": list_channels,
    "get_tutorial": get_tutorial,
    "get_auth_flow": get_auth_flow,
    "list_models": list_models,
    "enable_channel": enable_channel,
    "set_field": set_field,
}


def call(name: str, args: dict) -> dict:
    fn = DISPATCH.get(name)
    if not fn:
        return {"ok": False, "error": f"未知工具 {name}"}
    try:
        return fn(**(args or {}))
    except Exception as e:  # 工具错误不该炸掉整个助手循环
        return {"ok": False, "error": str(e)}
