# -*- coding: utf-8 -*-
"""配置助手编排 —— 确定性意图路由 + LLM 工具调用循环。

设计要点：
  * 无 LLM 可用（用户还没配模型 key）时，助手不瘫痪——降级为确定性意图路由：
    「接入企业微信」「配 deepseek 模型」这类高频意图直接产出 plan（步骤 + 认证流程 + 教程）。
  * 有 LLM 时走工具调用循环：把用户消息 + 工具 schema 给 LLM，执行其请求的工具，回灌结果，
    直到 LLM 给出自然语言答复或达到步数上限。
  * 两条路径都只经 tools.call 操作引擎，副作用可控、可测。
"""
from __future__ import annotations

import json
import re
from typing import Optional

from . import tools
from .llm import LLMClient, LLMUnavailable

# 中文通道别名 → 通道 id（意图路由用）。
_CHANNEL_ALIASES = {
    "企业微信": "wecom", "微信": "openclaw-weixin", "wecom": "wecom",
    "飞书": "feishu", "feishu": "feishu", "telegram": "telegram", "电报": "telegram",
    "discord": "discord", "slack": "slack", "钉钉": None,
    "whatsapp": "whatsapp", "line": "line", "qq": "qqbot", "元宝": "yuanbao",
    "signal": "signal", "信号": "signal", "teams": "msteams",
}

# 厂商别名 → provider id。
_PROVIDER_ALIASES = {
    "deepseek": "deepseek", "深度求索": "deepseek", "openai": "openai",
    "gpt": "openai", "claude": "anthropic", "anthropic": "anthropic",
    "kimi": "moonshot", "月之暗面": "moonshot", "moonshot": "moonshot",
    "智谱": "zai", "glm": "zai", "zai": "zai", "豆包": "volcengine",
    "火山": "volcengine", "通义": "qwen", "千问": "qwen", "ollama": "ollama",
    "mistral": "mistral", "groq": "groq", "cohere": "cohere",
}


def _match(text: str, table: dict) -> Optional[str]:
    low = text.lower()
    # 长别名优先，避免「企业微信」被「微信」抢占。
    for alias in sorted(table, key=len, reverse=True):
        if alias.lower() in low:
            return table[alias]
    return None


def route_intent(message: str, agent: str = "openclaw") -> Optional[dict]:
    """确定性意图路由。命中返回 plan dict，未命中返回 None。"""
    ch = _match(message, _CHANNEL_ALIASES)
    if ch:
        flow = tools.get_auth_flow(ch, agent)
        tut = tools.get_tutorial(ch, agent)
        return {
            "kind": "channel_setup", "agent": agent, "channel": ch,
            "auth_flow": flow, "tutorial": tut,
            "reply": _channel_reply(tut, flow),
            "actions": [{"type": "open_auth_flow", "agent": agent, "channel": ch}],
        }
    prov = _match(message, _PROVIDER_ALIASES)
    if prov and any(k in message for k in ("模型", "model", "key", "配", "接入")):
        return {
            "kind": "model_setup", "agent": agent, "provider": prov,
            "reply": (f"要配置 {prov} 模型：在「模型」页选择 {prov}，填入 API Key 后点"
                      f"「获取模型」即可从下拉里选主模型，无需手打。"),
            "actions": [{"type": "open_model_panel", "agent": agent, "provider": prov}],
        }
    return None


def _channel_reply(tut: dict, flow: dict) -> str:
    label = tut.get("label") or flow.get("target")
    kind = flow.get("kind")
    intro = {
        "qr": f"要接入{label}：启用后点「开始扫码」，用手机扫码登录即可。",
        "token": f"要接入{label}：需要先拿到凭据（{('、'.join(tut.get('credential_fields') or []) or '见教程')}），填入后保存。",
        "code": f"要接入{label}：启用后发消息获取配对码，填入即可。",
        "webhook": f"要接入{label}：把本页的 Webhook 地址填到对端后台。",
        "oauth": f"要接入{label}：点授权链接完成登录授权。",
        "builtin": f"{label}是内置通道，启用并保存即可。",
    }.get(kind, f"要接入{label}，请按下方步骤操作。")
    steps = tut.get("steps") or []
    numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))
    return intro + ("\n\n步骤：\n" + numbered if numbered else "")


def respond(message: str, *, agent: str = "openclaw",
            llm: Optional[LLMClient] = None, max_steps: int = 4) -> dict:
    """助手主入口。有 LLM 走工具循环；无 LLM 或 LLM 失败降级到意图路由。"""
    if llm is None:
        plan = route_intent(message, agent)
        if plan:
            return {"mode": "intent", **plan}
        return {"mode": "intent", "kind": "fallback",
                "reply": "请先在「模型」页配置一个模型 API Key，之后我就能用自然语言帮你完成配置。"
                         "你也可以直接说「接入企业微信」「配 deepseek 模型」，我会给出步骤。",
                "actions": []}
    try:
        return _llm_loop(message, agent, llm, max_steps)
    except LLMUnavailable:
        plan = route_intent(message, agent)
        return {"mode": "intent_degraded",
                **(plan or {"kind": "fallback",
                            "reply": "模型暂不可用，已降级到内置引导。请直接说「接入<通道>」或「配<厂商>模型」。",
                            "actions": []})}


_SYSTEM = ("你是 chatop 智能体配置助手。用户想配置 openclaw / hermes 等智能体的模型与通道。"
           "用提供的工具查询通道、教程、认证流程、模型清单，或代为启用通道/设置字段。"
           "涉及密钥等敏感信息时，只引导用户在界面填写，不要凭空编造凭据。"
           "最终用简体中文简洁答复，并说明用户下一步该点什么。")


def _llm_loop(message: str, agent: str, llm: LLMClient, max_steps: int) -> dict:
    messages = [{"role": "system", "content": _SYSTEM},
                {"role": "user", "content": message}]
    used_tools = []
    for _ in range(max_steps):
        out = llm.chat(messages, tools.SCHEMAS)
        calls = out.get("tool_calls") or []
        if not calls:
            return {"mode": "llm", "reply": out.get("content") or "",
                    "tools_used": used_tools, "actions": []}
        messages.append({"role": "assistant", "content": out.get("content") or "",
                         "tool_calls": calls})
        for tc in calls:
            fn = (tc.get("function") or {})
            name = fn.get("name") or ""
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            args.setdefault("agent", agent) if name in ("list_channels", "enable_channel",
                                                          "set_field", "get_tutorial",
                                                          "get_auth_flow") else None
            result = tools.call(name, args)
            used_tools.append({"name": name, "args": args})
            messages.append({"role": "tool", "tool_call_id": tc.get("id") or name,
                             "content": json.dumps(result, ensure_ascii=False)})
    # 步数用尽，最后再要一次自然语言总结。
    out = llm.chat(messages, None)
    return {"mode": "llm", "reply": out.get("content") or "（已达到步数上限）",
            "tools_used": used_tools, "actions": []}
