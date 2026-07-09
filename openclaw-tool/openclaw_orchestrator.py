#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OpenClaw 配置器 — 一步到位编排 + 一键全自动（无 tkinter）。

设计（对齐 spec，决策 C 混合 + 模型策略 A）：
  - 长任务（装插件 / channels login）在**终端**跑，日志可见；终端把输出写日志文件。
  - GUI 端 watcher 读日志，抽取二维码 ASCII → 交给 openclaw_qr 渲染成弹窗图片。
  - 状态机按通道 auth 类型分支；每步错误停在原地给可读原因；二维码抓不到 → 保底提示终端扫码。

副作用（终端、轮询、UI 回填）以可注入回调提供，核心决策逻辑是纯函数、可单测。
"""
import json
import os
import re
import subprocess

import openclaw_catalog

HANDOFF_DIR = "/tmp"

# —— 状态机 ——
S_START = "START"
S_PRECHECK = "PRECHECK"
S_PLUGIN = "PLUGIN_INSTALL"
S_AUTH = "AUTH"          # 按 auth 分支：qr login / token fill / webhook / oauth / builtin
S_POLL = "POLL_CONNECT"
S_CONNECTED = "CONNECTED"
S_TIMEOUT = "TIMEOUT"
S_FAILED = "FAILED"
S_QR_FALLBACK = "QR_FALLBACK"   # 二维码抓不到 → 引导终端扫码

# 线性推进 + 错误旁路。next_state 是纯函数，便于单测。
_LINEAR = {S_START: S_PRECHECK, S_PRECHECK: S_PLUGIN, S_PLUGIN: S_AUTH, S_AUTH: S_POLL,
           S_POLL: S_CONNECTED}


def next_state(state, event):
    """状态转移（纯函数）。event ∈ {ok, fail, timeout, qr_missing}。"""
    if event == "fail":
        return S_FAILED
    if event == "timeout":
        return S_TIMEOUT
    if event == "qr_missing":
        return S_QR_FALLBACK
    if event == "ok":
        return _LINEAR.get(state, state)
    return state


def _channel_entry(channel_key, catalog=None):
    catalog = catalog or openclaw_catalog.load_catalog()
    for entry in catalog["channels"]:
        if entry.id == channel_key:
            return entry
    return None


def plugin_pkg_for(channel_key, catalog=None):
    """通道的 npm 包名 —— 从 openclaw 的官方插件目录取，**绝不拼接 `@openclaw/<id>`**。

    企业微信/微信/元宝/Zalo ClawBot 由第三方厂商发布，包名不遵守该模式。旧的
    PLUGIN_MAP 硬编码表按模式假设手抄，恰好漏掉这四个，并凭空写出 raft/webchat/
    voice-call/bluebubbles 等 openclaw 根本不提供的通道。
    内置通道（imessage / telegram）返回 None。
    """
    entry = _channel_entry(channel_key, catalog)
    return entry.npm_spec if entry else None


def handoff_path(channel_key):
    """终端子进程把 QR/状态写到这里，GUI watcher 轮询读取。"""
    return os.path.join(HANDOFF_DIR, "openclaw-oneclick-%s.json" % channel_key)


def build_login_cmd(channel_key, account=None):
    """`openclaw channels login` 是 openclaw 自带的扫码/授权入口（`--help` 实证）。"""
    cmd = ["channels", "login", "--channel", channel_key]
    if account:
        cmd += ["--account", account]
    return cmd


def read_handoff(path):
    """读交接文件；不存在 / 半截写入 → None（不抛异常）。"""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def build_login_script(channel_key, auth, pkg, log_path, skill_install_delay=0):
    """构造终端里要跑的 bash（纯函数，可单测）：先加载 nvm，可选装插件，
    再按 auth 执行 login/启用；全部输出 tee 到 log_path 供 GUI 抽二维码/状态。

    装插件走 `openclaw plugins install`（openclaw 自己的机制，校验完整性），
    不用裸 `npm i -g` —— 后者绕过 openclaw 的 expectedIntegrity 校验。
    """
    parts = [
        'nvm_sh="${NVM_DIR:-$HOME/.nvm}/nvm.sh"',
        '[ -s "$nvm_sh" ] && . "$nvm_sh"',
        f'echo "=== openclaw 一步到位: {channel_key} ===" | tee "{log_path}"',
    ]
    if pkg:
        parts.append(f'echo "[1/3] 安装插件 {pkg} ..." | tee -a "{log_path}"')
        parts.append(f'openclaw plugins install {pkg} 2>&1 | tee -a "{log_path}"')
    if auth == "qr":
        parts.append(f'echo "[2/3] 扫码登录，请用手机扫描下方二维码 ..." | tee -a "{log_path}"')
        login = " ".join(build_login_cmd(channel_key))
        parts.append(f'openclaw {login} 2>&1 | tee -a "{log_path}"')
    elif auth == "builtin":
        parts.append(f'echo "[2/3] 启用内置通道 {channel_key} ..." | tee -a "{log_path}"')
    parts.append(f'echo "[done] 完成，可关闭本窗口" | tee -a "{log_path}"')
    return " ; ".join(parts)


# —— 二维码从混合日志里抽取（纯函数）——
_QR_LINE_CHARS = set("█▀▄▓▒░ ")


def extract_qr_block(text):
    """从终端日志里抽出连续的 ASCII 二维码块（块字符占主导的连续多行）。取最长一段。"""
    if not text:
        return None
    best, cur = [], []
    for ln in text.splitlines():
        s = ln.rstrip("\n")
        blocks = sum(1 for c in s if c in "█▀▄▓▒░")
        is_qr = blocks >= 8 and all(c in _QR_LINE_CHARS for c in s if c != "\t")
        if is_qr:
            cur.append(s)
        else:
            if len(cur) > len(best):
                best = cur
            cur = []
    if len(cur) > len(best):
        best = cur
    return "\n".join(best) if len(best) >= 9 else None


def detect_ollama_default(cmd_runner):
    """模型兜底（策略 A）：探测本地 ollama 已装模型，返回 'ollama/<name>' 或 None。"""
    ok, out = cmd_runner("ollama list", 10)
    if not ok or not out:
        return None
    for line in out.splitlines()[1:]:  # 跳过表头
        name = line.split()[0] if line.split() else ""
        if name and "/" not in name.replace(":", "/").split("/")[0]:
            return f"ollama/{name}"
    return None


# ---------------------------------------------------------------------------
# 编排：单通道一步到位
# ---------------------------------------------------------------------------
class OneStop:
    """单通道一步到位会话。副作用全走注入回调，便于测试与复用。
    cmd_runner(cmd, timeout)->(ok,out); terminal_runner(bash_inner, title)->None;
    status_probe()->{ch:connected}; ui(event, **data); qr_capture(log_text)->(src,matrix)|None
    """
    def __init__(self, *, cmd_runner, terminal_runner, status_probe, ui,
                 qr_capture=None, network_check=None, gateway_check=None,
                 handoff_dir="/tmp"):
        self.cmd_runner = cmd_runner
        self.terminal_runner = terminal_runner
        self.status_probe = status_probe
        self.ui = ui
        self.qr_capture = qr_capture
        self.network_check = network_check or (lambda: True)
        self.gateway_check = gateway_check or (lambda: True)
        self.handoff_dir = handoff_dir
        self.state = S_START

    def _emit(self, event, **data):
        if self.ui:
            self.ui(event, channel=data.pop("channel", None), state=self.state, **data)

    def log_path(self, channel_key):
        safe = re.sub(r"[^\w.-]", "_", channel_key)
        return os.path.join(self.handoff_dir, f"openclaw-oneclick-{safe}.log")

    def run(self, channel_key, auth):
        self.state = S_PRECHECK
        # 1. PRECHECK
        if not self.network_check():
            self.state = S_FAILED
            self._emit("precheck_fail", channel=channel_key, reason="网络不可达，装插件会失败")
            return self.state
        if not self.gateway_check():
            self._emit("warn", channel=channel_key, reason="网关未运行，配置后请先启动网关")
        # 2. 起终端跑「装插件(+login)」长任务
        pkg = plugin_pkg_for(channel_key)
        log = self.log_path(channel_key)
        try:
            os.path.exists(log) and os.remove(log)
        except Exception:
            pass
        self.state = S_PLUGIN
        inner = build_login_script(channel_key, auth, pkg, log)
        self._emit("terminal_launch", channel=channel_key, auth=auth)
        self.terminal_runner(inner, f"OpenClaw 配置 {channel_key}")
        # 3. auth 分支
        self.state = S_AUTH
        if auth == "qr":
            self._await_qr(channel_key, log)
        elif auth == "token":
            self._emit("fill_token", channel=channel_key)   # GUI 聚焦字段 + 开取证链接
            return self.state
        elif auth == "webhook":
            self._emit("show_webhook", channel=channel_key)
            return self.state
        elif auth == "oauth":
            self._emit("open_oauth", channel=channel_key)
            return self.state
        # builtin 直接进轮询
        # 4. 轮询连接
        return self._poll(channel_key)

    def _await_qr(self, channel_key, log, tries=40, sleep=1.0):
        """等待终端把二维码写进日志，抽取并交 GUI 渲染；抓不到 → 保底。"""
        import time
        for _ in range(tries):
            try:
                text = open(log, encoding="utf-8", errors="ignore").read() if os.path.exists(log) else ""
            except Exception:
                text = ""
            block = extract_qr_block(text)
            if block:
                cap = None
                if self.qr_capture:
                    cap = self.qr_capture({"qr_ascii": block})
                if cap and cap[1]:
                    self._emit("qr_ready", channel=channel_key, source=cap[0], matrix=cap[1])
                    return
                self._emit("qr_ready", channel=channel_key, source="ascii_raw", ascii=block)
                return
            time.sleep(sleep)
        self.state = S_QR_FALLBACK
        self._emit("qr_missing", channel=channel_key,
                   reason="未能抓到二维码，请在弹出的终端窗口里直接扫码")

    def _poll(self, channel_key, tries=60, sleep=2.0):
        import time
        for _ in range(tries):
            conn = self.status_probe() or {}
            if conn.get(channel_key) or conn.get(channel_key.replace("openclaw-", "")):
                self.state = S_CONNECTED
                self._emit("connected", channel=channel_key)
                return self.state
            time.sleep(sleep)
        self.state = S_TIMEOUT
        self._emit("timeout", channel=channel_key,
                   reason="超时未检测到连接，可能仍在连接中，稍后刷新一览")
        return self.state


# ---------------------------------------------------------------------------
# 一键全自动
# ---------------------------------------------------------------------------
def run_all(config, enabled_channels, auth_of, *, cmd_runner, terminal_runner,
            status_probe, ui, ensure_openclaw, start_gateway, set_model,
            has_credentials, network_check=None, gateway_check=None, handoff_dir="/tmp"):
    """一键全自动顺序：环境→模型兜底(仅未配置)→起网关→遍历已启用通道。
    需要人的（扫码/无凭据 token）不阻塞，收尾汇总。返回结果清单。
    """
    results = []
    ui("phase", phase="环境检查")
    ensure_openclaw()

    # 模型兜底（策略 A：仅未配置时）
    primary = (((config.get("agents") or {}).get("defaults") or {}).get("model") or {}).get("primary", "")
    if not str(primary).strip():
        ui("phase", phase="模型兜底")
        model = detect_ollama_default(cmd_runner)
        if model:
            set_model(model)
            ui("info", msg=f"已将默认模型兜底为 {model}")
        else:
            ui("info", msg="未探测到本地 Ollama 模型，请到「模型」页手动配置")

    ui("phase", phase="启动网关")
    start_gateway()

    ui("phase", phase="配置通道")
    conn = status_probe() or {}
    for ch_key, ch_name in enabled_channels:
        if conn.get(ch_key) or conn.get(ch_key.replace("openclaw-", "")):
            results.append((ch_key, "已连接"))
            continue
        auth = auth_of(ch_key)
        if auth == "token" and not has_credentials(ch_key):
            results.append((ch_key, "待填 Token"))   # 不阻塞
            continue
        sess = OneStop(cmd_runner=cmd_runner, terminal_runner=terminal_runner,
                       status_probe=status_probe, ui=ui, network_check=network_check,
                       gateway_check=gateway_check, handoff_dir=handoff_dir)
        st = sess.run(ch_key, auth)
        results.append((ch_key, "已连接" if st == S_CONNECTED else st))
    ui("summary", results=results)
    return results


# ---------- P3：配置闭环（校验 → 起网关 → 探活） ----------

VERIFY_STEPS = (
    ("config_validate", ["config", "validate"], 30),
    ("gateway_start", ["gateway", "start"], 120),
    ("gateway_probe", ["gateway", "probe"], 30),
)


def _default_cli_runner(cmd, timeout=30):
    """通过登录 shell 跑 openclaw（GUI 由 .desktop 拉起时 PATH 无 nvm/npm-global）。"""
    inner = 'nvm_sh="${NVM_DIR:-$HOME/.nvm}/nvm.sh"; [ -s "$nvm_sh" ] && . "$nvm_sh"; openclaw ' + " ".join(cmd)
    proc = subprocess.Popen(["bash", "-lc", inner], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    out, _ = proc.communicate(timeout=timeout)
    return proc.returncode, out.decode("utf-8", "replace")


def verify_and_start(runner=None, on_progress=None):
    """配置 → 校验 → 起网关 → 探活。任一步失败即停在原地并给出可读原因。

    顺序不可调：配置非法时若先起网关，真正的原因会被「网关启动失败」掩盖，
    用户看到的是症状不是根因。
    """
    runner = runner or _default_cli_runner
    for name, cmd, timeout in VERIFY_STEPS:
        if on_progress:
            on_progress(name, "running")
        rc, out = runner(cmd, timeout=timeout)
        if rc != 0:
            if on_progress:
                on_progress(name, "failed")
            return {"ok": False, "failed_step": name,
                    "detail": (out or "").strip()[-600:] or "无输出"}
        if on_progress:
            on_progress(name, "ok")
    return {"ok": True, "failed_step": None, "detail": "配置已生效，网关可达"}
