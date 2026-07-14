# -*- coding: utf-8 -*-
"""配置引擎核心类型 —— 纯 stdlib，无 UI / 无 FastAPI 依赖。

用 dataclass（py3.7+；宿主与 station venv 均为 3.10/3.11，可用）。所有类型都提供
`to_dict()` 便于 station 路由直接 JSON 序列化——引擎不 import pydantic/fastapi。

字段命名对齐前端契约：kind / secret / apply_url 等直接进 JSON 给 React 消费。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


# —— 认证/字段种类枚举（用普通常量，避免 enum 序列化包袱）——
# 字段控件种类
FIELD_TEXT = "text"
FIELD_SECRET = "secret"       # 密钥类，前端 type=password，脱敏回显
FIELD_SELECT = "select"
FIELD_BOOL = "bool"
FIELD_MODEL = "model"         # 模型选择器（配合 models 服务的下拉）

# 认证流程种类 —— 前端据此决定「就地出什么交互」
AUTH_QR = "qr"                # 扫码（微信/企业微信/WhatsApp）
AUTH_TOKEN = "token"          # 填 Token/凭据表单
AUTH_CODE = "code"            # 填验证码/配对码
AUTH_WEBHOOK = "webhook"      # 展示 webhook 地址供对端填写
AUTH_OAUTH = "oauth"          # 跳转授权
AUTH_BUILTIN = "builtin"      # 内置通道，启用即可，无需外部凭据

# 诊断级别
LEVEL_OK = "ok"
LEVEL_WARN = "warn"
LEVEL_ERROR = "error"

# 模型来源
SRC_LIVE = "live"             # 实时从厂商 API 拉取
SRC_SNAPSHOT = "snapshot"     # 烤入快照兜底


@dataclass
class FieldSpec:
    key: str
    label: str
    kind: str = FIELD_TEXT
    secret: bool = False
    help: str = ""
    options: list[str] = field(default_factory=list)   # select 用
    apply_url: Optional[str] = None                     # 「去哪申请凭据」
    placeholder: str = ""
    value: Any = None                                   # 当前值（secret 时为脱敏视图）
    advanced: bool = False                              # 高级字段——默认折叠，非主字段

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChannelSummary:
    """通道卡片摘要——描述面里通道组的一项。"""
    id: str
    label: str
    auth: str
    enabled: bool = False
    installed: bool = True
    configured: bool = False
    supports_qr: bool = False
    apply_url: Optional[str] = None
    has_tutorial: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Group:
    id: str
    label: str
    fields: list[FieldSpec] = field(default_factory=list)
    channels: list[ChannelSummary] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "fields": [f.to_dict() for f in self.fields],
            "channels": [c.to_dict() for c in self.channels],
        }


@dataclass
class AgentDescriptor:
    id: str
    label: str
    groups: list[Group] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"id": self.id, "label": self.label,
                "groups": [g.to_dict() for g in self.groups]}


@dataclass
class AgentStatus:
    id: str
    label: str
    installed: bool = False
    configured: bool = False
    running: bool = False
    version: Optional[str] = None
    model: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AuthFlowDescriptor:
    """启用某通道/凭据后「就地出什么交互」的唯一契约。

    kind=qr    → 前端画二维码卡片，start 后经 SSE 收 qr matrix
    kind=token → 渲染 fields 表单（Token/AppID/Secret…）
    kind=code  → 先发起配对，再填验证码/配对码（fields 里有 code 字段）
    kind=webhook → 展示 webhook_url 供对端后台填写
    kind=oauth → 打开 apply_url 授权
    kind=builtin → 无需外部凭据，enable 即可
    """
    kind: str
    target: str                                    # 通道 id
    label: str = ""
    fields: list[FieldSpec] = field(default_factory=list)
    apply_url: Optional[str] = None
    tutorial_id: Optional[str] = None
    webhook_url: Optional[str] = None
    cmd: Optional[list[str]] = None                # qr/code 的 openclaw 子命令
    hint: str = ""
    free_kv: bool = False                          # schema 空壳通道——前端走自由键值编辑

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ApplyResult:
    ok: bool
    removed: list[str] = field(default_factory=list)     # sanitize 移除项
    diagnostics: list["Diagnostic"] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict:
        return {"ok": self.ok, "removed": list(self.removed),
                "diagnostics": [d.to_dict() for d in self.diagnostics],
                "message": self.message}


@dataclass
class Diagnostic:
    id: str
    level: str
    message: str
    auto_fix: Optional[str] = None                 # 可执行的自愈动作标识；None 表示无

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ModelInfo:
    key: str                                       # 形如 provider/model
    label: str = ""
    source: str = SRC_LIVE

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Event:
    """引擎外发事件——station 桥接到 EventHub/SSE，tkinter 桥接到回调，测试收进 list。"""
    type: str
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"type": self.type, **self.data}
