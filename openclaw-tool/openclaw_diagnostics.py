#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""OpenClaw 配置器 — 体检/诊断模块（纯逻辑，无 tkinter）。

probe(config, env) 返回体检清单，每项：
  {"key","name","status":"ok|fail|warn","detail","fix":descriptor|None,"fix_label"}
`fix` 是**修复描述符字符串**（如 "install_openclaw"、"config_channel:openclaw-weixin"），
由 GUI 层解析成实际动作（起终端 / 调 orchestrator）。诊断层不含 GUI/编排依赖，便于单测。

依赖以「可注入」方式提供，默认惰性复用 openclaw_config_gui 里已修好的函数；
测试可传 mock。
"""
import json
import os
import socket
from pathlib import Path


# ---------------------------------------------------------------------------
# 可注入的底层探针（默认实现）
# ---------------------------------------------------------------------------
def _default_gateway_check(port):
    """TCP 端口判活（与 GUI 已修的 check_gateway_running 同口径）。"""
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=2):
            return True
    except Exception:
        return False


def _default_cmd_runner(cmd, timeout=20):
    """经登录 shell + nvm 执行命令，返回 (ok, output)。默认惰性复用 GUI 的实现，
    失败/无法导入时退化为本地 bash -lc + nvm。"""
    try:
        from openclaw_config_gui import run_openclaw_cmd_sync
        return run_openclaw_cmd_sync(cmd, timeout=timeout)
    except Exception:
        import subprocess
        nvm_sh = Path(os.environ.get("NVM_DIR", str(Path.home() / ".nvm"))) / "nvm.sh"
        nvm_load = f'[ -s "{nvm_sh}" ] && . "{nvm_sh}" ; ' if nvm_sh.exists() else ""
        try:
            r = subprocess.run(["bash", "-lc", nvm_load + cmd], capture_output=True,
                               text=True, timeout=timeout, cwd=os.path.expanduser("~"))
            out = (r.stdout or "") + (r.stderr or "")
            return r.returncode == 0, out.strip()
        except Exception as e:
            return False, str(e)


def _default_network_check():
    for url in ("registry.npmjs.org", "www.npmjs.com"):
        try:
            with socket.create_connection((url, 443), timeout=5):
                return True
        except Exception:
            continue
    return False


def status_json(cmd_runner=None):
    """跑 `openclaw status --json` 并解析出末尾 JSON 对象。失败返回 None。"""
    cmd_runner = cmd_runner or _default_cmd_runner
    ok, out = cmd_runner("openclaw status --json", 20)
    if not ok or not out:
        return None
    out = out.strip()
    try:
        return json.loads(out)          # 纯净输出直接解析
    except Exception:
        pass
    start = out.find("{")               # 混有警告时取**第一个** { 做括号配平（取顶层对象，
    if start < 0:                       # 不能用 rfind——那会落到内层子对象上）
        return None
    depth = 0
    for i in range(start, len(out)):
        if out[i] == "{":
            depth += 1
        elif out[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(out[start:i + 1])
                except Exception:
                    return None
    return None


def _connected_channels(status):
    """从 status json 的 channelSummary 提取每通道连接态 → {key: connected_bool}。
    channelSummary 形态未逐一写死，做宽松解析：条目可能是 str 或 dict。"""
    result = {}
    if not status:
        return result
    for entry in status.get("channelSummary") or []:
        if isinstance(entry, dict):
            key = entry.get("channel") or entry.get("id") or entry.get("name")
            conn = entry.get("connected")
            if conn is None:
                conn = str(entry.get("status", "")).lower() in ("connected", "online", "ready", "ok")
            if key:
                result[str(key)] = bool(conn)
        elif isinstance(entry, str):
            low = entry.lower()
            connected = any(w in low for w in ("connected", "online", "ready", "ok"))
            # 尝试从 "wechat: connected" 里取 key
            key = entry.split(":")[0].strip() if ":" in entry else entry.strip()
            if key:
                result[key] = connected
    return result


# ---------------------------------------------------------------------------
# 主体：probe
# ---------------------------------------------------------------------------
def probe(config, env=None, *, gateway_check=None, cmd_runner=None,
          network_check=None, enabled_channels=None):
    """生成体检清单。config: 解析后的 openclaw.json dict。
    enabled_channels: [(key, 显示名)]，已启用通道列表（GUI 传入，避免耦合注册表）。"""
    env = env if env is not None else os.environ
    gateway_check = gateway_check or _default_gateway_check
    cmd_runner = cmd_runner or _default_cmd_runner
    network_check = network_check or _default_network_check
    config = config or {}
    items = []

    # 1. Node 环境。判据只看「node 能不能跑」——nvm 只是安装 node 的方式之一，
    # 镜像里也可能是 npm-global / 系统 node。要求 nvm.sh 存在会对后者误报 FAIL。
    node_ok, node_out = cmd_runner("node -v", 10)
    if node_ok:
        nvm_sh = Path(env.get("NVM_DIR", str(Path.home() / ".nvm"))) / "nvm.sh"
        via = "nvm" if nvm_sh.exists() else "系统/npm-global"
        items.append({"key": "node", "name": "Node 环境", "status": "ok",
                      "detail": f"Node {node_out.strip()}（{via}）", "fix": None, "fix_label": ""})
    else:
        items.append({"key": "node", "name": "Node 环境", "status": "fail",
                      "detail": "node 不可用（openclaw 依赖它）",
                      "fix": "install_node", "fix_label": "安装 Node"})

    # 2. openclaw 已安装
    ocl_ok, ocl_out = cmd_runner("openclaw --version", 10)
    if ocl_ok:
        items.append({"key": "openclaw", "name": "openclaw 已安装", "status": "ok",
                      "detail": (ocl_out.splitlines() or [""])[0][:40], "fix": None, "fix_label": ""})
    else:
        items.append({"key": "openclaw", "name": "openclaw 已安装", "status": "fail",
                      "detail": "命令不可用（PATH 无 openclaw）",
                      "fix": "install_openclaw", "fix_label": "安装 openclaw"})

    # 3. 网关运行
    port = (config.get("gateway") or {}).get("port", 18789)
    if gateway_check(port):
        items.append({"key": "gateway", "name": "网关运行", "status": "ok",
                      "detail": f"端口 {port} 监听中", "fix": None, "fix_label": ""})
    else:
        items.append({"key": "gateway", "name": "网关运行", "status": "fail",
                      "detail": f"端口 {port} 未监听",
                      "fix": "start_gateway", "fix_label": "启动网关"})

    # 4. 模型可用（空 → warn，因一键会兜底；非空 → ok）
    primary = (((config.get("agents") or {}).get("defaults") or {}).get("model") or {}).get("primary", "")
    if str(primary).strip():
        items.append({"key": "model", "name": "模型已配置", "status": "ok",
                      "detail": str(primary), "fix": None, "fix_label": ""})
    else:
        items.append({"key": "model", "name": "模型已配置", "status": "warn",
                      "detail": "主模型未设置（一键将探测 Ollama 兜底）",
                      "fix": "fix_model", "fix_label": "配置模型"})

    # 5. 工作区
    ws = (((config.get("agents") or {}).get("defaults") or {}).get("workspace")) or ""
    ws_path = os.path.expanduser(str(ws)) if ws else ""
    if ws_path and os.path.isdir(ws_path) and os.access(ws_path, os.W_OK):
        items.append({"key": "workspace", "name": "工作区", "status": "ok",
                      "detail": ws_path, "fix": None, "fix_label": ""})
    else:
        items.append({"key": "workspace", "name": "工作区", "status": "fail",
                      "detail": (ws_path or "未设置") + "（不存在或不可写）",
                      "fix": "make_workspace", "fix_label": "创建工作区"})

    # 6. 各已启用通道连接（依赖网关在跑）
    if enabled_channels:
        conn_map = _connected_channels(status_json(cmd_runner)) if gateway_check(port) else {}
        for ch_key, ch_name in enabled_channels:
            connected = conn_map.get(ch_key)
            if connected is None:
                connected = conn_map.get(ch_key.replace("openclaw-", ""))
            if connected:
                items.append({"key": f"ch:{ch_key}", "name": f"通道 {ch_name}", "status": "ok",
                              "detail": "已连接", "fix": None, "fix_label": ""})
            else:
                items.append({"key": f"ch:{ch_key}", "name": f"通道 {ch_name}", "status": "fail",
                              "detail": "未连接",
                              "fix": f"config_channel:{ch_key}", "fix_label": "一步到位配置"})

    # 7. 网络（装插件前提）— warn 级
    if not network_check():
        items.append({"key": "network", "name": "网络（npm 源）", "status": "warn",
                      "detail": "npm 源不可达，装插件会失败",
                      "fix": "check_network", "fix_label": "重试检测"})
    else:
        items.append({"key": "network", "name": "网络（npm 源）", "status": "ok",
                      "detail": "npm 源可达", "fix": None, "fix_label": ""})

    return items


# ---------- P3：openclaw 自带的校验/探活命令 ----------
# 三条命令均已在容器内实证存在（openclaw 2026.6.10）：
#   config validate  —— 不启网关，纯 schema 校验
#   gateway probe    —— 可达性 + 认证能力 + 读探针
#   doctor --json    —— 诊断并可 --fix 修复

def _validate_runner(cmd, timeout=30):
    """跑 openclaw 子命令，返回 (rc, 合并输出)。走登录 shell 以加载 nvm/npm-global。"""
    import subprocess
    inner = ('nvm_sh="${NVM_DIR:-$HOME/.nvm}/nvm.sh"; [ -s "$nvm_sh" ] && . "$nvm_sh"; '
             "openclaw " + " ".join(cmd))
    proc = subprocess.Popen(["bash", "-lc", inner], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    out, _ = proc.communicate(timeout=timeout)
    return proc.returncode, out.decode("utf-8", "replace")


def check_config_valid(runner=None):
    """`openclaw config validate` —— 不启网关，纯 schema 校验。

    放在起网关之前：配置非法时若先起网关，真正的原因会被「网关启动失败」掩盖。
    """
    runner = runner or _validate_runner
    rc, out = runner(["config", "validate"], timeout=30)
    if rc == 0:
        return {"key": "config_valid", "name": "配置合法性", "status": "ok",
                "detail": "配置通过 schema 校验", "fix": None, "fix_label": None}
    return {"key": "config_valid", "name": "配置合法性", "status": "fail",
            "detail": (out or "").strip()[-400:] or "校验失败（无输出）",
            "fix": None, "fix_label": "查看详情"}


def check_gateway_probe(runner=None):
    """`openclaw gateway probe` —— 网关可达性与认证能力。"""
    runner = runner or _validate_runner
    rc, out = runner(["gateway", "probe"], timeout=30)
    return {"key": "gateway_probe", "name": "网关可达性",
            "status": "ok" if rc == 0 else "fail",
            "detail": (out or "").strip()[-400:], "fix": None, "fix_label": None}
