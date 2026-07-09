#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""openclaw-tool 新模块单元测试（本机可跑，不依赖 tkinter/openclaw/qrcode）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import openclaw_qr as qr
import openclaw_diagnostics as diag
import openclaw_orchestrator as orch


def _framed_matrix():
    """21x21：四周一圈 1（避免被空白边裁剪），内部一个可辨识图案。"""
    n = 21
    m = [[0] * n for _ in range(n)]
    for i in range(n):
        m[0][i] = m[n - 1][i] = m[i][0] = m[i][n - 1] = 1
    for i in range(6, 15):
        m[10][i] = 1
        m[i][10] = 1
    return m


# ---- openclaw_qr ----
def test_qr_fullblock_roundtrip():
    m = _framed_matrix()
    ascii_block = qr.matrix_to_ascii(m, dark="██", light="  ")
    parsed = qr.parse_ascii_qr(ascii_block)
    assert parsed == m, "全块 ASCII 往返应还原矩阵"


def test_qr_halfblock_parse():
    # 含 ▀▄ 才会走半块模式：6 文本行 × 12 字符 → 展开成 12×12。
    # █=上下黑, ▀=上黑下白, ▄=上白下黑
    text = "\n".join(["█▀▄█▀▄█▀▄█▀▄"] * 6)
    m = qr.parse_ascii_qr(text)
    assert m is not None and len(m[0]) == 12
    assert len(m) == 12
    assert m[0] == [1, 1, 0, 1, 1, 0, 1, 1, 0, 1, 1, 0]  # 上半行：█▀→1,▄→0


def test_qr_garbage_returns_none():
    assert qr.parse_ascii_qr("hello world\nnot a qr") is None
    assert qr.parse_ascii_qr("") is None


def test_qr_encode_without_lib_is_none_or_matrix():
    r = qr.encode_to_matrix("https://example.com")
    assert r is None or (isinstance(r, list) and r and isinstance(r[0], list))


# ---- orchestrator ----
def test_next_state_linear_and_errors():
    assert orch.next_state(orch.S_START, "ok") == orch.S_PRECHECK
    assert orch.next_state(orch.S_PLUGIN, "ok") == orch.S_AUTH
    assert orch.next_state(orch.S_AUTH, "fail") == orch.S_FAILED
    assert orch.next_state(orch.S_AUTH, "qr_missing") == orch.S_QR_FALLBACK
    assert orch.next_state(orch.S_POLL, "timeout") == orch.S_TIMEOUT


def test_plugin_map():
    assert orch.plugin_pkg_for("feishu") == "@openclaw/feishu"
    assert orch.plugin_pkg_for("openclaw-weixin") is None   # 内置不装插件
    assert orch.plugin_pkg_for("webchat") is None


def test_build_login_script_qr_has_login_and_tee():
    s = orch.build_login_script("openclaw-weixin", "qr", None, "/tmp/x.log")
    assert "channels login --channel openclaw-weixin" in s
    assert "/tmp/x.log" in s and "nvm" in s


def test_build_login_script_token_installs_plugin_no_login():
    s = orch.build_login_script("feishu", "token", "@openclaw/feishu", "/tmp/f.log")
    assert "npm i -g @openclaw/feishu" in s
    assert "channels login" not in s


def test_extract_qr_block_from_mixed_log():
    log = "starting...\n[1/3] install\n" + "\n".join(["██████████"] * 12) + "\ndone\n"
    block = orch.extract_qr_block(log)
    assert block is not None and block.count("\n") == 11


def test_detect_ollama_default():
    def runner(cmd, t=10):
        return True, "NAME            ID    SIZE\nqwen3-coder:7b  abc   4GB\n"
    assert orch.detect_ollama_default(runner) == "ollama/qwen3-coder:7b"

    def empty(cmd, t=10):
        return False, ""
    assert orch.detect_ollama_default(empty) is None


# ---- diagnostics ----
def _runner_all_ok(cmd, timeout=20):
    if cmd == "node -v":
        return True, "v20.10.0"
    if cmd == "openclaw --version":
        return True, "openclaw 1.2.3"
    if "status --json" in cmd:
        return True, '{"gateway":{"reachable":true},"channelSummary":[{"channel":"telegram","connected":true}]}'
    return True, ""


def test_probe_all_green_when_ok(tmp_path=None):
    cfg = {"gateway": {"port": 18789},
           "agents": {"defaults": {"model": {"primary": "ollama/qwen3-coder"},
                                    "workspace": os.path.expanduser("~")}}}
    items = diag.probe(cfg, gateway_check=lambda p: True, cmd_runner=_runner_all_ok,
                       network_check=lambda: True,
                       enabled_channels=[("telegram", "电报(Telegram)")])
    by = {i["key"]: i for i in items}
    assert by["openclaw"]["status"] == "ok"
    assert by["gateway"]["status"] == "ok"
    assert by["model"]["status"] == "ok"
    assert by["ch:telegram"]["status"] == "ok"


def test_probe_node_ok_without_nvm():
    """回归：容器用 npm-global/系统 node（无 ~/.nvm）时，Node 环境不得误报 FAIL。"""
    def runner(cmd, timeout=20):
        if cmd == "node -v":
            return True, "v20.10.0"
        if cmd == "openclaw --version":
            return True, "OpenClaw 2026.6.10"
        return True, ""
    items = diag.probe({"gateway": {"port": 18789}}, env={"NVM_DIR": "/nonexistent-nvm"},
                       gateway_check=lambda p: True, cmd_runner=runner, network_check=lambda: True)
    node = {i["key"]: i for i in items}["node"]
    assert node["status"] == "ok", f"无 nvm 但 node 可用应为 ok，实际 {node}"
    assert "npm-global" in node["detail"] or "系统" in node["detail"]


def test_probe_flags_failures():
    def runner(cmd, timeout=20):
        if cmd == "openclaw --version":
            return False, "command not found"
        if cmd == "node -v":
            return False, ""
        if "status --json" in cmd:
            return False, ""
        return True, ""
    cfg = {"gateway": {"port": 18789}, "agents": {"defaults": {"model": {"primary": ""}}}}
    items = diag.probe(cfg, gateway_check=lambda p: False, cmd_runner=runner,
                       network_check=lambda: False,
                       enabled_channels=[("openclaw-weixin", "微信(Weixin)")])
    by = {i["key"]: i for i in items}
    assert by["openclaw"]["status"] == "fail" and by["openclaw"]["fix"] == "install_openclaw"
    assert by["gateway"]["status"] == "fail" and by["gateway"]["fix"] == "start_gateway"
    assert by["model"]["status"] == "warn"       # 空模型 warn（一键会兜底）
    assert by["network"]["status"] == "warn"
    assert by["ch:openclaw-weixin"]["fix"] == "config_channel:openclaw-weixin"


if __name__ == "__main__":
    import traceback
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"PASS {t.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {t.__name__}")
            traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
