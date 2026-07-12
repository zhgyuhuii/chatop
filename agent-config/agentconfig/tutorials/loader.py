# -*- coding: utf-8 -*-
"""教程库加载器 —— 烤入结构化教程为主，官方文档链接为辅。

data.json 每条通道：
  {id, label, auth, steps[], credential_fields[], apply_url, docs_url, troubleshooting[]}

缺失通道回退通用兜底（按 auth 类型给通用步骤 + 官方 docs 链接），永不返回空。
"""
from __future__ import annotations

import json
import os
from typing import Optional

_DATA_PATH = os.path.join(os.path.dirname(__file__), "data.json")
_CACHE = {"data": None}


def _load() -> dict:
    if _CACHE["data"] is None:
        try:
            with open(_DATA_PATH, encoding="utf-8") as fh:
                _CACHE["data"] = json.load(fh)
        except Exception:
            _CACHE["data"] = {"openclaw": {}}
    return _CACHE["data"]


# auth → 通用兜底步骤
_GENERIC = {
    "qr": ["在本页启用该通道并保存配置。", "点「开始扫码」，用对应 App 扫描二维码完成登录。",
           "扫码成功后回到总览，该通道会显示已连接。"],
    "token": ["到该平台的开发者后台创建应用/机器人，获取凭据。", "在本页填写凭据并保存配置。",
              "启动网关；如通道走配对，按提示在对话里输入配对码。"],
    "code": ["启用通道并保存后，向机器人发送消息获取配对码。", "在本页填入配对码完成配对。"],
    "webhook": ["复制本页显示的 Webhook 地址。", "到对端后台填入该地址并保存。"],
    "oauth": ["点授权链接，登录并授权。", "授权完成后返回本页。"],
    "builtin": ["内置通道，在本页启用并保存即可，无需外部凭据。"],
}


def channel_ids(agent: str = "openclaw") -> list[str]:
    return list((_load().get(agent) or {}).keys())


def get(agent: str, channel: str, auth: Optional[str] = None) -> dict:
    entry = (_load().get(agent) or {}).get(channel)
    if entry:
        out = dict(entry)
        out["source"] = "baked"
        return out
    a = auth or "token"
    return {
        "id": channel, "label": channel, "auth": a,
        "steps": list(_GENERIC.get(a, _GENERIC["token"])),
        "credential_fields": [], "apply_url": None,
        "docs_url": f"https://docs.openclaw.ai/channels/{channel}",
        "troubleshooting": ["查看日志：openclaw logs --follow，向机器人发消息观察输出。"],
        "source": "generic",
    }


def all_for(agent: str = "openclaw") -> dict:
    return dict(_load().get(agent) or {})


def reset_cache() -> None:
    _CACHE["data"] = None
