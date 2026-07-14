# -*- coding: utf-8 -*-
"""把 agent-config 引擎的 FieldSpec 映射为 tkinter 控件类型，tkinter 配置器据此建表单，
不再手抄 channels 字段。引擎 import 失败（离线/未装）时纯函数仍可用，field_rows_* 回落空表，
调用方保留原手抄路径兜底。"""
from __future__ import annotations


def widget_kind(spec) -> str:
    """FieldSpec → tk 控件类型标签。secret→密文 Entry；bool→Checkbutton；
    select（有 options）→Combobox；其余（text/number/model）→Entry。"""
    if getattr(spec, "secret", False) or getattr(spec, "kind", "") == "secret":
        return "entry_secret"
    kind = getattr(spec, "kind", "text")
    if kind == "bool":
        return "checkbutton"
    if kind == "select" and getattr(spec, "options", None):
        return "combobox"
    return "entry"  # text / number / model / 未知 一律单行输入


def _adapter(home=None):
    """尝试构造引擎 openclaw 适配器；不可用返回 None（离线兜底）。"""
    try:
        from agentconfig.adapters.openclaw_adapter import OpenClawAdapter
    except Exception:
        return None
    try:
        return OpenClawAdapter(home=home) if home else OpenClawAdapter()
    except Exception:
        return None


def field_rows_for_channel(channel: str, home=None) -> list:
    """返回 [(FieldSpec, widget_kind), ...]；引擎不可用或该通道无字段时返回 []。"""
    ad = _adapter(home)
    if ad is None:
        return []
    try:
        flow = ad.auth_flow(channel)
    except Exception:
        return []
    fields = getattr(flow, "fields", None) or []
    return [(f, widget_kind(f)) for f in fields]
