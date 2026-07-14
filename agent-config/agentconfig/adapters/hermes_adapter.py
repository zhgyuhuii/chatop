# -*- coding: utf-8 -*-
"""Hermes 配置适配器 —— 第二个实例，用于验证适配器抽象没抽歪。

Hermes 配置面比 openclaw 小：`~/.hermes/config.yaml`（或 .json/.env）里的 API Key、
模型、基础开关。一期不解析 Hermes 内部 schema，用**烤入字段表**（同 openclaw 目录快照思路）。

配置文件优先 JSON（引擎无 yaml 依赖）。若现存的是 yaml，读取时降级为「不可解析」诊断，
引导用户用 hermes setup 终端兜底——不擅自改动 yaml 语义。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from ..core.types import (AgentDescriptor, AgentStatus, ApplyResult,
                          AuthFlowDescriptor, Diagnostic, Event, FieldSpec,
                          Group)
from ..core.types import (AUTH_BUILTIN, AUTH_TOKEN, FIELD_BOOL, FIELD_MODEL,
                          FIELD_NUMBER, FIELD_SECRET, FIELD_SELECT, FIELD_TEXT,
                          LEVEL_ERROR, LEVEL_OK, LEVEL_WARN)

# 烤入字段表：(key, 中文名, kind, secret, help, options, apply_url)
_FIELDS = [
    ("api_key", "Hermes / Nous API Key", FIELD_SECRET, True,
     "Nous Research 控制台申请的 API Key。", [],
     "https://hermes-agent.nousresearch.com/"),
    ("model", "模型", FIELD_MODEL, False,
     "Hermes 使用的模型；可从「模型」页拉取清单。", [], None),
    ("temperature", "采样温度", FIELD_NUMBER, False,
     "0–2，越大越发散。默认 0.7。", [], None),
    ("auto_approve", "自动批准工具调用", FIELD_BOOL, False,
     "开启后 Hermes 执行工具无需逐次确认（谨慎）。", [], None),
]


class HermesAdapter:
    id = "hermes"
    label = "Hermes"

    def __init__(self, home: Optional[str] = None):
        self.home = Path(home or os.environ.get("HOME", "/home/admin"))

    @property
    def config_dir(self) -> Path:
        return self.home / ".hermes"

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.json"

    def _yaml_present(self) -> bool:
        return (self.config_dir / "config.yaml").exists() and not self.config_file.exists()

    # ---------- describe ----------
    def describe(self) -> AgentDescriptor:
        cfg = self.read_config(redact=True)
        g = Group(id="basic", label="基础")
        for key, label, kind, secret, help_, options, apply_url in _FIELDS:
            g.fields.append(FieldSpec(
                key=key, label=label, kind=kind, secret=secret, help=help_,
                options=list(options), apply_url=apply_url,
                value=cfg.get(key) if not secret else _redact(cfg.get(key))))
        return AgentDescriptor(id=self.id, label=self.label, groups=[g])

    # ---------- status ----------
    def status(self) -> AgentStatus:
        cfg = self.read_config(redact=True)
        configured = bool(cfg) and "_load_error" not in cfg and bool(cfg.get("api_key"))
        return AgentStatus(id=self.id, label=self.label,
                           installed=self._installed(), configured=configured,
                           running=self._running(), version=None,
                           model=cfg.get("model") if isinstance(cfg, dict) else None)

    def _installed(self) -> bool:
        if self.config_dir.exists():
            return True
        from .openclaw_adapter import _on_path
        return _on_path("hermes")

    def _running(self) -> bool:
        # Hermes 是常驻型；无稳定端口约定，一期不探进程，返回 False（总览页可另接 station 探测）。
        return False

    # ---------- 配置读写 ----------
    def read_config(self, *, redact: bool = True) -> dict:
        if self._yaml_present():
            return {"_load_error": "现存 config.yaml，引擎不解析 YAML；请用 hermes setup 或改用 config.json"}
        if not self.config_file.exists():
            return {}
        try:
            with open(self.config_file, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except Exception as e:
            return {"_load_error": str(e)}
        if not isinstance(cfg, dict):
            return {"_load_error": "配置根不是对象"}
        if redact and cfg.get("api_key"):
            cfg = dict(cfg)
            cfg["api_key"] = _redact(cfg["api_key"])
        return cfg

    def apply(self, patch: dict) -> ApplyResult:
        if self._yaml_present():
            return ApplyResult(ok=False, message="存在 config.yaml，请先迁移到 config.json 或用 hermes setup")
        current = self.read_config(redact=False)
        if "_load_error" in current:
            current = {}
        allowed = {f[0] for f in _FIELDS}
        merged = dict(current)
        for k, v in (patch or {}).items():
            if k in allowed:
                merged[k] = v
        self.config_dir.mkdir(parents=True, exist_ok=True)
        tmp = str(self.config_file) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.config_file)
        return ApplyResult(ok=True, message="已写入 ~/.hermes/config.json")

    # ---------- 认证流程 ----------
    def auth_flow(self, target: str) -> AuthFlowDescriptor:
        # Hermes 无外部聊天通道概念；认证=填 API Key。
        return AuthFlowDescriptor(
            kind=AUTH_TOKEN, target="api_key", label="Hermes API Key",
            fields=[FieldSpec(key="api_key", label="API Key", kind=FIELD_SECRET,
                             secret=True)],
            apply_url="https://hermes-agent.nousresearch.com/",
            hint="填入 API Key 后保存即可。")

    def run_flow(self, target: str, inputs: dict, emit) -> None:
        emit(Event("flow_noop", {"agent": "hermes",
                                 "message": "Hermes 仅需填 API Key，无需扫码。"}))

    # ---------- 体检 ----------
    def health_check(self) -> list[Diagnostic]:
        diags: list[Diagnostic] = []
        if not self._installed():
            diags.append(Diagnostic(id="not_installed", level=LEVEL_WARN,
                                    message="未检测到 Hermes，可从应用市场安装",
                                    auto_fix=None))
        cfg = self.read_config(redact=True)
        if "_load_error" in cfg:
            diags.append(Diagnostic(id="config_broken", level=LEVEL_ERROR,
                                    message=cfg["_load_error"], auto_fix="hermes_setup"))
            return diags
        if not cfg.get("api_key"):
            diags.append(Diagnostic(id="no_key", level=LEVEL_WARN,
                                    message="尚未配置 API Key", auto_fix=None))
        if not cfg.get("model"):
            diags.append(Diagnostic(id="no_model", level=LEVEL_WARN,
                                    message="尚未选择模型", auto_fix=None))
        if not diags:
            diags.append(Diagnostic(id="healthy", level=LEVEL_OK, message="配置健康"))
        return diags


def _redact(v):
    if not isinstance(v, str) or not v:
        return v
    return "***" + v[-2:] if len(v) > 2 else "***"
