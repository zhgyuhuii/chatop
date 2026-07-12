# -*- coding: utf-8 -*-
"""LLM 客户端抽象 —— 纯 stdlib（urllib）。

- LLMClient 协议：chat(messages, tools) -> {"content": str, "tool_calls": [...]}。
- OpenAICompatClient：打 OpenAI 兼容 /chat/completions，复用用户已在 openclaw 配好的
  provider + key（不自带 key）。
- FakeLLMClient：测试用，脚本化返回。

助手在无可用模型时降级为确定性意图路由（planner），不依赖本模块。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable, Optional, Protocol


class LLMClient(Protocol):
    def chat(self, messages: list[dict], tools: Optional[list[dict]] = None) -> dict:
        ...


class LLMUnavailable(RuntimeError):
    pass


class OpenAICompatClient:
    """OpenAI 兼容 chat completions 客户端。"""

    def __init__(self, base_url: str, api_key: str, model: str,
                 opener: Optional[Callable] = None, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self._opener = opener or self._default_opener

    def _default_opener(self, url, headers, payload, timeout):
        req = urllib.request.Request(url, data=payload,
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                return resp.getcode(), resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read() if hasattr(e, "read") else b""
        except Exception as e:
            raise LLMUnavailable(str(e))

    def chat(self, messages: list[dict], tools: Optional[list[dict]] = None) -> dict:
        body = {"model": self.model, "messages": messages}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        payload = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {self.api_key}"}
        code, raw = self._opener(self.base_url + "/chat/completions",
                                 headers, payload, self.timeout)
        if code != 200:
            raise LLMUnavailable(f"LLM 接口 HTTP {code}: {raw[:200]!r}")
        data = json.loads(raw.decode("utf-8", "replace"))
        msg = (data.get("choices") or [{}])[0].get("message") or {}
        return {"content": msg.get("content") or "",
                "tool_calls": msg.get("tool_calls") or []}


class FakeLLMClient:
    """测试替身：按预设脚本逐轮返回。script 是 [{"content":..,"tool_calls":..}, ...]。"""

    def __init__(self, script: list[dict]):
        self.script = list(script)
        self.calls: list[dict] = []

    def chat(self, messages: list[dict], tools: Optional[list[dict]] = None) -> dict:
        self.calls.append({"messages": messages, "tools": tools})
        if not self.script:
            return {"content": "（无更多脚本）", "tool_calls": []}
        return self.script.pop(0)


def from_openclaw_config(cfg: dict, model_base: Optional[dict] = None,
                         opener: Optional[Callable] = None) -> Optional["LLMClient"]:
    """从 openclaw 配置构造 LLM 客户端，用用户已配的主模型 + 该 provider 的 key。

    cfg：openclaw.json（未脱敏）。model_base：{provider: (base_url,)} 覆盖表。
    无主模型 / 无 key 时返回 None（助手据此降级）。
    """
    primary = (((cfg.get("agents") or {}).get("defaults") or {})
               .get("model") or {}).get("primary", "") or ""
    if "/" not in primary:
        return None
    provider = primary.split("/", 1)[0]
    from ..models.providers import _ENDPOINTS
    ep = _ENDPOINTS.get(provider)
    if not ep:
        return None
    base = ep[0]
    # key：openclaw 把 provider key 放在 models.providers.<id>.apiKey 或环境变量。
    key = (((cfg.get("models") or {}).get("providers") or {}).get(provider) or {}).get("apiKey")
    if not key:
        return None
    return OpenAICompatClient(base_url=base, api_key=key, model=primary, opener=opener)
