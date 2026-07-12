# -*- coding: utf-8 -*-
"""定位并导入 openclaw-tool 的纯 stdlib 模块（单一真源，不复制）。

openclaw-tool 里 openclaw_catalog / openclaw_orchestrator / openclaw_qr / catalog_overrides
都是纯 stdlib、import 时不调 CLI、不 import tkinter，可被引擎直接复用。

路径解析：优先 env OPENCLAW_TOOL_DIR；否则试镜像路径 /opt/openclaw-tool 与仓内相对路径。
解析失败时抛 OpenClawToolMissing——上层 openclaw 适配器据此降级为「不可用」而非整体崩。
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path


class OpenClawToolMissing(RuntimeError):
    pass


def _candidates() -> list[Path]:
    out = []
    env = os.environ.get("OPENCLAW_TOOL_DIR")
    if env:
        out.append(Path(env))
    out.append(Path("/opt/openclaw-tool"))
    # 仓内相对：agent-config/agentconfig/adapters/ → 上溯到 /work/chatop/openclaw-tool
    here = Path(__file__).resolve()
    for up in here.parents:
        cand = up / "openclaw-tool"
        if cand.is_dir():
            out.append(cand)
            break
    return out


_LOADED = {"dir": None}


def _ensure_on_path() -> Path:
    if _LOADED["dir"] is not None:
        return _LOADED["dir"]
    for cand in _candidates():
        if (cand / "openclaw_catalog.py").is_file():
            if str(cand) not in sys.path:
                sys.path.insert(0, str(cand))
            _LOADED["dir"] = cand
            return cand
    raise OpenClawToolMissing(
        "未找到 openclaw-tool（设 OPENCLAW_TOOL_DIR 或置于 /opt/openclaw-tool）")


def load(module_name: str):
    _ensure_on_path()
    return importlib.import_module(module_name)


def available() -> bool:
    try:
        _ensure_on_path()
        return True
    except OpenClawToolMissing:
        return False
