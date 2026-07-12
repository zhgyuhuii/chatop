# -*- coding: utf-8 -*-
"""模型清单智能获取 —— 填 API Key → 验证有效性 → 拉取该厂商可用模型清单。

纯 stdlib（urllib）。绝大多数厂商是 OpenAI 兼容 `GET {base}/models`；少数用私有端点。
拉取失败（网络/401/私有协议）时回退烤入快照 snapshot.json，`source=snapshot`，
并给出可读原因——保证前端永不空白。

opener 可注入，便于单测（不发真网）。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Callable, Optional

from ..core.types import ModelInfo, SRC_LIVE, SRC_SNAPSHOT

_SNAPSHOT_PATH = os.path.join(os.path.dirname(__file__), "snapshot.json")

# 各 provider 的模型列表端点。多数 OpenAI 兼容：GET base/models，Bearer 认证。
# (base_url, auth_header_fmt, list_kind)；list_kind: "openai" | "ollama" | "anthropic"
_ENDPOINTS = {
    "openai": ("https://api.openai.com/v1", "Bearer {key}", "openai"),
    "deepseek": ("https://api.deepseek.com/v1", "Bearer {key}", "openai"),
    "moonshot": ("https://api.moonshot.cn/v1", "Bearer {key}", "openai"),
    "mistral": ("https://api.mistral.ai/v1", "Bearer {key}", "openai"),
    "groq": ("https://api.groq.com/openai/v1", "Bearer {key}", "openai"),
    "together": ("https://api.together.xyz/v1", "Bearer {key}", "openai"),
    "fireworks": ("https://api.fireworks.ai/inference/v1", "Bearer {key}", "openai"),
    "openrouter": ("https://openrouter.ai/api/v1", "Bearer {key}", "openai"),
    "xai": ("https://api.x.ai/v1", "Bearer {key}", "openai"),
    "zai": ("https://open.bigmodel.cn/api/paas/v4", "Bearer {key}", "openai"),
    "volcengine": ("https://ark.cn-beijing.volces.com/api/v3", "Bearer {key}", "openai"),
    "cohere": ("https://api.cohere.com/v1", "Bearer {key}", "cohere"),
    "anthropic": ("https://api.anthropic.com/v1", "x-api-key:{key}", "anthropic"),
    "ollama": ("http://127.0.0.1:11434", None, "ollama"),
    "ollama-cloud": ("https://ollama.com", "Bearer {key}", "ollama"),
}


def _default_opener(url: str, headers: dict, timeout: float = 8.0) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.getcode(), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read() if hasattr(e, "read") else b""
    except Exception as e:  # 网络不可达 / 超时 / DNS
        return 0, str(e).encode("utf-8", "replace")


def load_snapshot() -> list[dict]:
    try:
        with open(_SNAPSHOT_PATH, encoding="utf-8") as fh:
            return (json.load(fh) or {}).get("models") or []
    except Exception:
        return []


def _snapshot_for(provider: str) -> list[ModelInfo]:
    prefix = provider + "/"
    out = []
    for m in load_snapshot():
        key = (m or {}).get("key") or ""
        if key.startswith(prefix):
            out.append(ModelInfo(key=key, label=key.split("/", 1)[1],
                                 source=SRC_SNAPSHOT))
    return out


def _parse_models(kind: str, provider: str, body: bytes) -> list[ModelInfo]:
    try:
        data = json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return []
    ids = []
    if kind in ("openai", "anthropic"):
        for m in (data.get("data") or data.get("models") or []):
            mid = m.get("id") if isinstance(m, dict) else None
            if mid:
                ids.append(mid)
    elif kind == "ollama":
        for m in (data.get("models") or []):
            name = m.get("name") or m.get("model") if isinstance(m, dict) else None
            if name:
                ids.append(name)
    elif kind == "cohere":
        for m in (data.get("models") or []):
            name = m.get("name") if isinstance(m, dict) else None
            if name:
                ids.append(name)
    return [ModelInfo(key=f"{provider}/{i}", label=i, source=SRC_LIVE) for i in ids]


def verify_and_list(provider: str, api_key: str = "", base_url: Optional[str] = None,
                    opener: Callable = _default_opener) -> dict:
    """填 key → 验证 → 拉清单。返回 {ok, source, models, reason}。

    - 端点未知：直接回退快照，reason 说明。
    - HTTP 200 且解析到模型：live 清单。
    - 401/403：key 无效，回退快照，reason 明确。
    - 其它失败：回退快照，reason 给原因。
    """
    ep = _ENDPOINTS.get(provider)
    if not ep:
        snap = _snapshot_for(provider)
        return _result(bool(snap), SRC_SNAPSHOT, snap,
                       f"未内置 {provider} 的模型端点，返回快照清单")

    ep_base, auth_fmt, kind = ep
    base = (base_url or ep_base).rstrip("/")
    url = base + ("/models" if kind in ("openai", "anthropic", "cohere") else "/api/tags")
    headers = {"Accept": "application/json"}
    if auth_fmt and api_key:
        if auth_fmt.startswith("x-api-key"):
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
        else:
            headers["Authorization"] = auth_fmt.format(key=api_key)
    elif auth_fmt and not api_key and provider != "ollama":
        snap = _snapshot_for(provider)
        return _result(bool(snap), SRC_SNAPSHOT, snap, "未提供 API Key，返回快照清单")

    code, body = opener(url, headers)
    if code == 200:
        models = _parse_models(kind, provider, body)
        if models:
            return _result(True, SRC_LIVE, models, "")
        snap = _snapshot_for(provider)
        return _result(bool(snap), SRC_SNAPSHOT, snap, "接口返回空清单，回退快照")
    if code in (401, 403):
        snap = _snapshot_for(provider)
        return _result(False, SRC_SNAPSHOT, snap, "API Key 无效或无权限（HTTP %d）" % code)
    if code == 0:
        snap = _snapshot_for(provider)
        return _result(bool(snap), SRC_SNAPSHOT, snap,
                       "网络不可达：" + body.decode("utf-8", "replace")[:120])
    snap = _snapshot_for(provider)
    return _result(bool(snap), SRC_SNAPSHOT, snap, "接口返回 HTTP %d，回退快照" % code)


def _result(ok: bool, source: str, models: list[ModelInfo], reason: str) -> dict:
    return {"ok": ok, "source": source,
            "models": [m.to_dict() for m in models], "reason": reason}
