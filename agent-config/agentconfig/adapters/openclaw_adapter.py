# -*- coding: utf-8 -*-
"""OpenClaw 配置适配器 —— 复用 openclaw-tool 的纯 stdlib 模块（单一真源，不复制）。

复用点：
  * openclaw_catalog.load_catalog / sanitize_config_for_gateway  —— 通道真源 + 落盘消毒
  * catalog_overrides.CHANNEL_AUTH / *_APPLY_URLS / MODEL_PROVIDERS —— 中文名/认证/申请链接
  * openclaw_orchestrator.OneStop / build_login_cmd / verify_and_start —— 扫码状态机 / 探活
  * openclaw_qr.build_matrix                                       —— 二维码抽取渲染

home 可参数化（默认 $HOME），便于用临时目录单测配置读写。
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Optional

from ..core.types import (AgentDescriptor, AgentStatus, ApplyResult,
                          AuthFlowDescriptor, ChannelSummary, Diagnostic,
                          Event, FieldSpec, Group, ModelInfo)
from ..core.types import (AUTH_BUILTIN, AUTH_OAUTH, AUTH_QR,
                          AUTH_TOKEN, AUTH_WEBHOOK, FIELD_MODEL, FIELD_SECRET,
                          FIELD_TEXT, LEVEL_ERROR, LEVEL_OK, LEVEL_WARN)
from . import _openclaw_tool as _tool


def _load(name):
    return _tool.load(name)


# openclaw 的通道 auth 到引擎 AuthFlow kind 的映射。openclaw pairing 类通道（telegram/
# discord/slack/feishu）本质是「填 Token 后再输配对码」——归为 token，配对码在教程/流程里补。
_AUTH_MAP = {
    "qr": AUTH_QR,
    "token": AUTH_TOKEN,
    "webhook": AUTH_WEBHOOK,
    "oauth": AUTH_OAUTH,
    "builtin": AUTH_BUILTIN,
}


class OpenClawAdapter:
    id = "openclaw"
    label = "OpenClaw"

    def __init__(self, home: Optional[str] = None, *,
                 qr_poll_tries: int = 60, qr_poll_interval: float = 1.0,
                 flow_spawn=None, sleep=None):
        self.home = Path(home or os.environ.get("HOME", "/home/admin"))
        # 扫码日志轮询参数（可注入，便于单测用极短值）。生产默认最多 ~60s 抓码。
        self.qr_poll_tries = qr_poll_tries
        self.qr_poll_interval = qr_poll_interval
        self._flow_spawn = flow_spawn        # (bash_script, log_path) -> None
        self._sleep = sleep or _real_sleep
        self._catalog_memo = None            # 目录（通道清单）按实例缓存：随 openclaw 版本变，
                                             # 运行期不变；避免每次 describe/auth_flow 重读+解析 JSON。

    # ---------- 路径 ----------
    @property
    def config_dir(self) -> Path:
        return self.home / ".openclaw"

    @property
    def config_file(self) -> Path:
        return self.config_dir / "openclaw.json"

    # ---------- 目录/能力 ----------
    @property
    def catalog_cache(self) -> Path:
        return self.home / ".cache/chatop/openclaw-catalog.json"

    def _catalog(self, force: bool = False):
        if self._catalog_memo is not None and not force:
            return self._catalog_memo
        cat = _load("openclaw_catalog")
        # 用 home 下缓存 + 出厂快照；两者皆无则静态兜底（0 通道）。
        self._catalog_memo = cat.load_catalog(cache_path=str(self.catalog_cache),
                                              factory_path=cat.FACTORY_PATH)
        return self._catalog_memo

    def _tutorial_ids(self) -> set:
        from ..tutorials import loader
        return set(loader.channel_ids("openclaw"))

    # ---------- describe ----------
    def describe(self) -> AgentDescriptor:
        groups: list[Group] = []
        cfg = self.read_config(redact=True)

        # 模型组
        ov = _load("catalog_overrides")
        primary = self._current_model(cfg)
        model_group = Group(id="model", label="模型")
        model_group.fields.append(FieldSpec(
            key="agents.defaults.model.primary", label="主模型", kind=FIELD_MODEL,
            help="填厂商 API Key 后可「获取模型」下拉选择，无需手打 provider/model。",
            value=primary))
        model_group.fields.append(FieldSpec(
            key="agents.defaults.model.fallbacks", label="备选模型", kind=FIELD_MODEL,
            help="主模型不可用时按序尝试，可多选。"))
        groups.append(model_group)

        # 通道组
        try:
            catalog = self._catalog()
            channels = catalog.get("channels") or []
        except Exception:
            channels = []
        tut = self._tutorial_ids()
        configured_ch = set((cfg.get("channels") or {}).keys())
        ch_group = Group(id="channels", label="通道")
        for ch in channels:
            ch_group.channels.append(ChannelSummary(
                id=ch.id, label=ch.label, auth=ch.auth,
                enabled=bool((cfg.get("channels", {}).get(ch.id) or {}).get("enabled")),
                installed=ch.installed, configured=ch.id in configured_ch,
                supports_qr=ch.supports_qr, apply_url=ch.apply_url,
                has_tutorial=ch.id in tut))
        groups.append(ch_group)

        # 网关组
        gw = Group(id="gateway", label="网关")
        gw.fields.append(FieldSpec(
            key="gateway.port", label="端口", kind=FIELD_TEXT,
            value=str((cfg.get("gateway") or {}).get("port", 18789)),
            placeholder="18789"))
        groups.append(gw)

        return AgentDescriptor(id=self.id, label=self.label, groups=groups)

    def _current_model(self, cfg: dict) -> str:
        return (((cfg.get("agents") or {}).get("defaults") or {})
                .get("model") or {}).get("primary", "") or ""

    # ---------- status ----------
    def status(self) -> AgentStatus:
        cfg = self.read_config(redact=True)
        configured = bool(cfg) and "_load_error" not in cfg
        version = self._version()
        running = self._gateway_running()
        return AgentStatus(id=self.id, label=self.label,
                           installed=self._installed(), configured=configured,
                           running=running, version=version,
                           model=self._current_model(cfg) or None)

    def _installed(self) -> bool:
        # 有配置文件或 openclaw 在 PATH 即视为已装（不调 CLI）。
        if self.config_file.exists():
            return True
        return _on_path("openclaw")

    def _version(self) -> Optional[str]:
        try:
            return (self._catalog().get("meta") or {}).get("openclaw_version")
        except Exception:
            return None

    def _gateway_running(self, port: int = 18789) -> bool:
        import socket
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            return False

    # ---------- 配置读写 ----------
    def read_config(self, *, redact: bool = True) -> dict:
        if not self.config_file.exists():
            return {}
        try:
            with open(self.config_file, encoding="utf-8") as fh:
                cfg = json.load(fh)
        except Exception as e:
            return {"_load_error": str(e)}
        if redact:
            cfg = _redact_secrets(cfg)
        return cfg

    def apply(self, patch: dict) -> ApplyResult:
        """深合并 patch 到现有配置 → sanitize → 原子写盘。返回移除项诊断。"""
        cat = _load("openclaw_catalog")
        current = self.read_config(redact=False)
        if "_load_error" in current:
            current = {}
        # 深拷贝 patch 再合并：_deep_merge 对「仅在 patch 里的键」直接引用不拷贝，
        # 而下面的 sanitize 会就地改 merged——不拷贝会连带改掉调用方的 patch，
        # 导致后面 _restore 读到的 patch 已被 sanitize 掏空。
        merged = _deep_merge(current, copy.deepcopy(patch or {}))
        # sanitize 会剥掉「只有 enabled、无实质字段」的通道桩——这对 token/qr 通道是对的
        # （缺凭据会让网关校验失败）。但 builtin 通道（imessage/clickclack 等）本就无需凭据，
        # {enabled:true} 即完整配置，不该被剥。先在 sanitize 前快照整份配置里已启用的 builtin
        # 通道（不只本次 patch——否则一次无关保存会把之前启用的 builtin 通道连带剥掉），
        # sanitize 后再恢复它们。sanitize 会就地改 merged，故必须在其之前取快照。
        builtin_enabled = self._enabled_builtin_channels(merged)
        sanitized, removed = cat.sanitize_config_for_gateway(merged)
        removed = self._restore_builtin_enables(builtin_enabled, sanitized, removed)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        tmp = str(self.config_file) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(sanitized, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.config_file)
        diags = [Diagnostic(id=f"removed:{r}", level=LEVEL_WARN,
                            message=f"移除未配全的残留：{r}") for r in removed]
        return ApplyResult(ok=True, removed=list(removed), diagnostics=diags,
                           message="已写入 ~/.openclaw/openclaw.json")

    def _enabled_builtin_channels(self, cfg: dict) -> list:
        """cfg 里已启用（enabled 真）且 auth==builtin 的通道 id 列表。
        builtin 判定用静态 catalog_overrides.CHANNEL_AUTH（无 CLI）。"""
        ch = ((cfg or {}).get("channels") or {})
        if not isinstance(ch, dict):
            return []
        ov = _load("catalog_overrides")
        out = []
        for cid, entry in ch.items():
            if cid == "defaults" or not isinstance(entry, dict):
                continue
            if entry.get("enabled") and ov.CHANNEL_AUTH.get(cid) == "builtin":
                out.append(cid)
        return out

    def _restore_builtin_enables(self, builtin_cids: list, sanitized: dict,
                                 removed: list) -> list:
        """把已启用的 builtin 通道保留回 sanitized，并从 removed 里摘掉。"""
        kept = list(removed)
        for cid in builtin_cids:
            token = "channels." + cid
            if token in kept:  # 被 sanitize 剥了 → 恢复
                sanitized.setdefault("channels", {})[cid] = {"enabled": True}
                kept.remove(token)
        return kept

    # ---------- 认证流程 ----------
    def auth_flow(self, target: str) -> AuthFlowDescriptor:
        ov = _load("catalog_overrides")
        try:
            entry = next((c for c in self._catalog()["channels"] if c.id == target), None)
        except Exception:
            entry = None
        raw_auth = (entry.auth if entry else ov.CHANNEL_AUTH.get(target, "token"))
        kind = _AUTH_MAP.get(raw_auth, AUTH_TOKEN)
        label = entry.label if entry else target
        apply_url = (entry.apply_url if entry else None) or ov.CHANNEL_APPLY_URLS.get(target)
        supports_qr = entry.supports_qr if entry else (target in ov.CHANNEL_QR_EXTRA)
        if supports_qr and kind == AUTH_TOKEN:
            kind = AUTH_QR
        tutorial_id = target if target in self._tutorial_ids() else None

        fields: list[FieldSpec] = []
        cmd = None
        hint = ""
        webhook_url = None
        if kind == AUTH_QR:
            orch = _load("openclaw_orchestrator")
            cmd = ["openclaw"] + orch.build_login_cmd(target)
            hint = "点「开始扫码」后用手机扫描二维码完成登录。"
        elif kind == AUTH_TOKEN:
            fields = _token_fields(target)
            hint = "填写下方凭据后保存；部分通道保存后还需在对话里输入配对码。"
        elif kind == AUTH_WEBHOOK:
            port = 18789
            webhook_url = f"http://<本机地址>:{port}/webhook/{target}"
            hint = "把上面的 Webhook 地址填到对端后台。"
        elif kind == AUTH_OAUTH:
            hint = "点链接完成授权登录。"
        elif kind == AUTH_BUILTIN:
            hint = "内置通道，启用即可，无需外部凭据。"

        return AuthFlowDescriptor(
            kind=kind, target=target, label=label, fields=fields,
            apply_url=apply_url, tutorial_id=tutorial_id, webhook_url=webhook_url,
            cmd=cmd, hint=hint)

    def run_flow(self, target: str, inputs: dict, emit) -> None:
        """扫码长任务（自包含、有界、事件驱动）。

        在后台起 `openclaw channels login` 子进程写日志，短间隔轮询日志抽二维码，
        抽到即 emit(flow:qr_ready, matrix)；超时 emit(flow:qr_missing)。**不做**分钟级
        连接轮询（连接状态由前端另行探活）——避免单次扫码阻塞数分钟。

        本方法通常由 station 放进线程执行，emit 经 call_soon_threadsafe 回灌 SSE。
        """
        # 安全硬校验：target 来自 HTTP 请求，且下面 build_login_script 会把它插进
        # `bash -lc` 执行的脚本（openclaw-tool 既有注入面）。通道 id 只可能是小写 slug，
        # 这里显式白名单化，杜绝任何 shell 元字符——不依赖后面 QR 分类的微妙性兜底。
        if not _CHANNEL_ID_RE.fullmatch(target or ""):
            emit(Event("flow:error", {"channel": target,
                                      "reason": "非法通道标识"}))
            return
        af = self.auth_flow(target)
        if af.kind != AUTH_QR:
            emit(Event("flow_noop", {"channel": target, "kind": af.kind,
                                     "message": "该通道无需扫码，请按表单填写凭据。"}))
            return
        orch = _load("openclaw_orchestrator")
        qr = _load("openclaw_qr")

        log_path = str(self.home / ".cache/chatop" / f"openclaw-login-{_safe(target)}.log")
        pkg = orch.plugin_pkg_for(target)
        script = orch.build_login_script(target, "qr", pkg, log_path)
        emit(Event("flow:terminal", {"channel": target, "log": log_path}))
        self._spawn_login(script, log_path)

        for _ in range(self.qr_poll_tries):
            try:
                text = open(log_path, encoding="utf-8", errors="ignore").read() \
                    if os.path.exists(log_path) else ""
            except OSError:
                text = ""
            block = orch.extract_qr_block(text)
            if block:
                try:
                    matrix = qr.parse_ascii_qr(block)
                except Exception:
                    matrix = None
                if matrix:
                    emit(Event("flow:qr_ready", {"channel": target, "matrix": matrix}))
                else:
                    emit(Event("flow:qr_ready", {"channel": target, "ascii": block}))
                return
            self._sleep(self.qr_poll_interval)
        emit(Event("flow:qr_missing", {"channel": target,
                                       "reason": "未抓到二维码，请在终端窗口扫码"}))

    def _spawn_login(self, script: str, log_path: str) -> None:
        if self._flow_spawn is not None:
            self._flow_spawn(script, log_path)
            return
        import subprocess
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        # 经登录 shell 跑（GUI 拉起时 PATH 无 nvm/npm-global）。日志由 script 内 tee 落盘。
        subprocess.Popen(["bash", "-lc", script], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ---------- 体检 ----------
    def health_check(self) -> list[Diagnostic]:
        diags: list[Diagnostic] = []
        cfg = self.read_config(redact=False)
        if "_load_error" in cfg:
            diags.append(Diagnostic(id="config_broken", level=LEVEL_ERROR,
                                    message="配置文件无法解析：" + cfg["_load_error"]))
            return diags
        # 配置消毒预演：有可移除的残留即报 warn（可自愈）。
        try:
            cat = _load("openclaw_catalog")
            _, removed = cat.sanitize_config_for_gateway(json.loads(json.dumps(cfg)))
        except Exception:
            removed = []
        for r in removed:
            diags.append(Diagnostic(id=f"stale:{r}", level=LEVEL_WARN,
                                    message=f"存在未配全残留 {r}，可能导致网关校验失败",
                                    auto_fix="sanitize"))
        if not self._current_model(cfg):
            diags.append(Diagnostic(id="no_model", level=LEVEL_WARN,
                                    message="尚未配置主模型，请到「模型」页选择",
                                    auto_fix=None))
        if not self._gateway_running():
            diags.append(Diagnostic(id="gateway_down", level=LEVEL_WARN,
                                    message="网关未运行，配置后请启动网关",
                                    auto_fix="start_gateway"))
        if not diags:
            diags.append(Diagnostic(id="healthy", level=LEVEL_OK, message="配置健康"))
        return diags


# ---------- helpers ----------

_SECRET_HINT = ("secret", "token", "apikey", "api_key", "apppassword",
                "password", "key")


def _is_secret_key(name: str) -> bool:
    low = name.lower()
    return any(h in low for h in _SECRET_HINT)


def _redact_secrets(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(v, str) and v and _is_secret_key(k):
                out[k] = "***" + v[-2:] if len(v) > 2 else "***"
            else:
                out[k] = _redact_secrets(v)
        return out
    if isinstance(obj, list):
        return [_redact_secrets(x) for x in obj]
    return obj


import re as _re

# 合法通道 id：openclaw 的通道 slug 全是小写字母/数字/连字符。用于扫码前硬校验，
# 防止 HTTP 传入的 channel 携带 shell 元字符注入 build_login_script 的 `bash -lc`。
_CHANNEL_ID_RE = _re.compile(r"[a-z0-9][a-z0-9-]*")


def _real_sleep(seconds: float) -> None:
    import time
    time.sleep(seconds)


def _safe(name: str) -> str:
    import re
    return re.sub(r"[^\w.-]", "_", name)


def _on_path(binary: str) -> bool:
    for p in os.environ.get("PATH", "").split(os.pathsep):
        if not p:
            continue
        try:
            if (Path(p) / binary).exists():
                return True
        except OSError:  # PATH 里可能有不可 stat 的目录
            continue
    return False


def _deep_merge(base, override):
    if not isinstance(base, dict) or not isinstance(override, dict):
        return override
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


# 各通道 Token 表单字段（openclaw schema 空壳的走自由键值；此处给常见通道的显式字段）。
_TOKEN_FIELDS = {
    "telegram": [("channels.telegram.botToken", "Bot Token", True)],
    "discord": [("channels.discord.token", "Bot Token", True)],
    "slack": [("channels.slack.botToken", "Bot Token (xoxb-)", True),
              ("channels.slack.appToken", "App Token (xapp-)", True)],
    "feishu": [("channels.feishu.appId", "App ID (cli_)", False),
               ("channels.feishu.appSecret", "App Secret", True)],
    "wecom": [("channels.wecom.corpId", "企业 ID (CorpID)", False),
              ("channels.wecom.agentId", "应用 AgentId", False),
              ("channels.wecom.secret", "应用 Secret", True)],
    "line": [("channels.line.channelAccessToken", "Channel Access Token", True),
             ("channels.line.channelSecret", "Channel Secret", True)],
    "qqbot": [("channels.qqbot.appId", "App ID", False),
              ("channels.qqbot.token", "Token", True),
              ("channels.qqbot.appSecret", "App Secret", True)],
}


def _token_fields(channel: str) -> list[FieldSpec]:
    specs = _TOKEN_FIELDS.get(channel)
    if not specs:
        return [FieldSpec(key=f"channels.{channel}.token", label="Token/凭据",
                         kind=FIELD_SECRET, secret=True,
                         help="该通道字段未在 openclaw schema 中显式定义，可填主凭据。")]
    return [FieldSpec(key=k, label=lbl,
                      kind=FIELD_SECRET if sec else FIELD_TEXT, secret=sec)
            for k, lbl, sec in specs]
