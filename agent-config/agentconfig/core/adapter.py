# -*- coding: utf-8 -*-
"""智能体配置适配器协议。

每个智能体（openclaw / hermes / …）实现一个 AgentAdapter。station 路由与 LLM 助手
只依赖这个协议，不关心具体智能体。副作用（子进程、事件）通过注入的 emit 回调外发，
保证 run_flow 之外的方法是可单测的纯读改写。
"""
from __future__ import annotations

from typing import Callable, Optional, Protocol, runtime_checkable

from .types import (AgentDescriptor, AgentStatus, ApplyResult,
                    AuthFlowDescriptor, Diagnostic, Event)

# emit(event) —— 引擎向外界推事件的唯一缝。
EmitFn = Callable[[Event], None]


@runtime_checkable
class AgentAdapter(Protocol):
    id: str
    label: str

    def describe(self) -> AgentDescriptor:
        """配置面板骨架（分组/字段/通道清单）。只读，不调 CLI（用烤入快照）。"""
        ...

    def status(self) -> AgentStatus:
        """安装/配置/运行三态 + 版本 + 当前主模型。"""
        ...

    def read_config(self, *, redact: bool = True) -> dict:
        """读磁盘配置真源；redact=True 时脱敏密钥字段。"""
        ...

    def apply(self, patch: dict) -> ApplyResult:
        """校验（sanitize）→ 写盘。返回移除项与诊断。不自动重启。"""
        ...

    def auth_flow(self, target: str) -> AuthFlowDescriptor:
        """某通道/凭据的认证流程描述符（前端据此渲染就地交互）。"""
        ...

    def run_flow(self, target: str, inputs: dict, emit: EmitFn) -> None:
        """执行认证长任务（扫码 login / 配对）；进度经 emit 外发。"""
        ...

    def health_check(self) -> list[Diagnostic]:
        """体检项 + 每项可选 auto_fix。"""
        ...
