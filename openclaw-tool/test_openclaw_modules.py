#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""openclaw-tool 新模块单元测试（本机可跑，不依赖 tkinter/openclaw/qrcode）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import openclaw_qr as qr
import openclaw_diagnostics as diag
import openclaw_orchestrator as orch
import openclaw_catalog as cat

import json
import shutil
import tempfile

_TESTDATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testdata")


def _fixture(name):
    with open(os.path.join(_TESTDATA, name), encoding="utf-8") as fh:
        return fh.read()


def _build_from_fixtures():
    return cat.build_catalog(
        channels_json=_fixture("channels-list.json"),
        schema_json=_fixture("config-schema-channels.json"),
        catalog_js=_fixture("plugin-catalog-snippet.js"),
        models_json=_fixture("models-list.json"),
        openclaw_version="2026.6.10",
    )


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


def test_plugin_pkg_from_catalog_not_guessed():
    """包名来自 openclaw 官方插件目录，不是 @openclaw/<id> 拼接。

    旧断言写着 `plugin_pkg_for("openclaw-weixin") is None  # 内置不装插件`——
    那是错的：微信是第三方发布的插件 @tencent-weixin/openclaw-weixin。
    """
    catalog = _build_from_fixtures()
    assert orch.plugin_pkg_for("feishu", catalog) == "@openclaw/feishu"
    assert orch.plugin_pkg_for("openclaw-weixin", catalog).startswith("@tencent-weixin/")
    assert orch.plugin_pkg_for("wecom", catalog).startswith("@wecom/")
    assert orch.plugin_pkg_for("telegram", catalog) is None   # 真·内置，无插件包
    assert orch.plugin_pkg_for("webchat", catalog) is None    # openclaw 不提供此通道


def test_build_login_script_qr_has_login_and_tee():
    s = orch.build_login_script("openclaw-weixin", "qr", None, "/tmp/x.log")
    assert "channels login --channel openclaw-weixin" in s
    assert "/tmp/x.log" in s and "nvm" in s


def test_build_login_script_token_installs_plugin_no_login():
    s = orch.build_login_script("feishu", "token", "@openclaw/feishu", "/tmp/f.log")
    # 走 openclaw plugins install，不用裸 npm i -g（后者绕过 expectedIntegrity 校验）
    assert "openclaw plugins install @openclaw/feishu" in s
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


# ---- openclaw_catalog: 官方插件目录解析 ----
def test_plugin_catalog_channel_packages_not_guessed():
    """四个第三方发布的包名不遵守 @openclaw/<id>，必须来自目录而非拼接。"""
    entries = cat.parse_plugin_catalog(_fixture("plugin-catalog-snippet.js"))
    chans = entries["channels"]
    assert chans["wecom"]["npm_spec"].startswith("@wecom/wecom-openclaw-plugin")
    assert chans["openclaw-weixin"]["npm_spec"].startswith("@tencent-weixin/openclaw-weixin")
    assert chans["yuanbao"]["npm_spec"].startswith("openclaw-plugin-yuanbao")
    assert chans["openclaw-zaloclawbot"]["npm_spec"].startswith("@zalo-platforms/openclaw-zaloclawbot")
    for cid, meta in chans.items():
        assert meta["npm_spec"], cid


def test_plugin_catalog_chinese_labels_from_openclaw():
    entries = cat.parse_plugin_catalog(_fixture("plugin-catalog-snippet.js"))
    assert entries["channels"]["wecom"]["label"] == "WeCom（企业微信）"
    assert "飞书" in entries["channels"]["feishu"]["label"]


def test_plugin_catalog_qr_marker():
    entries = cat.parse_plugin_catalog(_fixture("plugin-catalog-snippet.js"))
    assert entries["channels"]["whatsapp"]["supports_qr"] is True
    assert entries["channels"]["openclaw-zaloclawbot"]["supports_qr"] is True
    assert entries["channels"]["slack"]["supports_qr"] is False


def test_plugin_catalog_providers():
    entries = cat.parse_plugin_catalog(_fixture("plugin-catalog-snippet.js"))
    provs = entries["providers"]
    assert provs["amazon-bedrock"]["npm_spec"] == "@openclaw/amazon-bedrock-provider"
    assert provs["amazon-bedrock"]["label"] == "Amazon Bedrock"
    assert "qwen" in provs


def test_plugin_catalog_corrupt_input_is_not_fatal():
    assert cat.parse_plugin_catalog("this is not javascript {{{") == {"channels": {}, "providers": {}}


# ---- openclaw_catalog: CLI 输出解析 ----
def test_parse_channels_list():
    st = cat.parse_channels_list(_fixture("channels-list.json"))
    assert len(st) == 27
    assert st["wecom"] == {"installed": False, "configured": False, "accounts": ()}
    assert st["openclaw-weixin"] == {"installed": True, "configured": True, "accounts": ("default",)}


def test_parse_version_takes_number_not_commit_hash():
    """真实输出 `OpenClaw 2026.6.10 (aa69b12)`；split()[-1] 会拿到 commit 哈希。"""
    assert cat.parse_version("OpenClaw 2026.6.10 (aa69b12)") == "2026.6.10"
    assert cat.parse_version("openclaw 1.2.3") == "1.2.3"
    assert cat.parse_version("") is None


def test_parse_channels_list_bad_json():
    assert cat.parse_channels_list("not json") == {}


def test_parse_schema_channels():
    keys = cat.parse_schema_channels(_fixture("config-schema-channels.json"))
    assert len(keys) == 25
    assert "telegram" in keys and "qa-channel" in keys and "wecom" not in keys


# ---- openclaw_catalog: 合并 ----
def test_build_wecom_visible_with_correct_package():
    """本轮的核心缺陷：企业微信必须出现，且包名不是拼接出来的。"""
    chans = {c.id: c for c in _build_from_fixtures()["channels"]}
    w = chans["wecom"]
    assert w.origin == "plugin"
    assert w.installed is False
    assert w.npm_spec.startswith("@wecom/wecom-openclaw-plugin")
    assert w.label == "WeCom（企业微信）"
    assert w.has_schema is False   # 未装 → 无字段 → GUI 走自由键值编辑器


def test_build_rejects_channels_openclaw_does_not_offer():
    """CLI 是 id 权威。webchat/voice-call 根本不存在；raft 存在于插件目录但 openclaw
    不把它列为可用通道；qa-channel 在 schema 里但 CLI 不列（内部通道）。三类都不得出现。"""
    chans = {c.id: c for c in _build_from_fixtures()["channels"]}
    for absent in ("webchat", "voice-call", "zalo-personal"):
        assert absent not in chans
    assert "raft" not in chans         # 在 plugin catalog 里，但不在 channels list --all
    assert "qa-channel" not in chans   # 在 schema 里，但不在 channels list --all
    assert "zalouser" in chans         # 真实 id（旧表误写成 zalo-personal）


def test_build_origin_axis():
    """origin 由「插件目录里有无 install.npmSpec」决定，不取 CLI 的 origin 字段
    （后者只表示 configured/installable，是配置状态而非 builtin/plugin 轴）。"""
    chans = {c.id: c for c in _build_from_fixtures()["channels"]}
    assert len(chans) == 27
    builtin = sorted(c.id for c in chans.values() if c.origin == "builtin")
    assert builtin == ["imessage", "telegram"]
    assert sum(1 for c in chans.values() if c.origin == "plugin") == 25
    assert all(c.npm_spec for c in chans.values() if c.origin == "plugin")


def test_build_free_kv_fallback_targets():
    """只有这 3 个插件通道没有 schema 字段。"""
    chans = {c.id: c for c in _build_from_fixtures()["channels"]}
    no_schema = sorted(c.id for c in chans.values() if not c.has_schema)
    assert no_schema == ["openclaw-zaloclawbot", "wecom", "yuanbao"]


def test_build_label_priority_and_qr():
    chans = {c.id: c for c in _build_from_fixtures()["channels"]}
    assert chans["wecom"].label == "WeCom（企业微信）"     # openclaw 自带中文
    assert chans["telegram"].label == "Telegram"          # 无目录条目 → 本地表/id
    assert chans["whatsapp"].supports_qr is True          # 目录 "(QR link)"
    assert chans["openclaw-weixin"].supports_qr is True   # 目录无标记 → 本地补充
    assert chans["slack"].supports_qr is False


def test_provider_ids_corrected():
    provs = {p.id: p for p in _build_from_fixtures()["providers"]}
    assert "zai" in provs and "glm" not in provs        # GLM 的真实 id 是 zai
    assert "bedrock" not in provs                        # 真实 id 是 amazon-bedrock
    assert provs["amazon-bedrock"].origin == "plugin"    # 且是需安装的插件
    assert provs["amazon-bedrock"].npm_spec == "@openclaw/amazon-bedrock-provider"
    # zai 既在插件目录里、又能免安装列出 14 个 GLM 模型 → 必须判 builtin，
    # 否则会误导用户去装一个根本不需要的插件。
    assert provs["zai"].origin == "builtin" and provs["zai"].npm_spec is None
    assert provs["openai"].env_var == "OPENAI_API_KEY"


# ---- openclaw_catalog: 三级降级与原子写 ----
def test_load_catalog_three_tier():
    tmp = tempfile.mkdtemp()
    try:
        cache = os.path.join(tmp, "cache.json")
        factory = os.path.join(tmp, "factory.json")

        c = cat.load_catalog(cache_path=cache, factory_path=factory)
        assert c["meta"]["source"] == "fallback"
        assert c["channels"] == []
        assert any(p.id == "openai" for p in c["providers"])

        cat.save_catalog(factory, {"channels": [], "providers": [], "search": [],
                                   "meta": {"openclaw_version": "2026.6.10"}})
        c = cat.load_catalog(cache_path=cache, factory_path=factory)
        assert c["meta"]["source"] == "factory"

        cat.save_catalog(cache, {"channels": [], "providers": [], "search": [],
                                 "meta": {"openclaw_version": "9999.1.1"}})
        c = cat.load_catalog(cache_path=cache, factory_path=factory)
        assert c["meta"]["source"] == "cache"
        assert c["meta"]["openclaw_version"] == "9999.1.1"
    finally:
        shutil.rmtree(tmp)


def test_save_catalog_is_atomic_and_roundtrips_namedtuples():
    tmp = tempfile.mkdtemp()
    try:
        path = os.path.join(tmp, "c.json")
        cat.save_catalog(path, _build_from_fixtures())
        assert not os.path.exists(path + ".tmp")
        back = cat.load_catalog(cache_path=path, factory_path=os.path.join(tmp, "none.json"))
        chans = {c.id: c for c in back["channels"]}
        assert isinstance(back["channels"][0], cat.ChannelEntry)
        assert chans["wecom"].npm_spec.startswith("@wecom/")
        assert chans["wecom"].supports_qr is False
        assert chans["whatsapp"].supports_qr is True
        assert chans["openclaw-weixin"].accounts == ("default",)
    finally:
        shutil.rmtree(tmp)


def test_load_catalog_corrupt_cache_falls_through():
    tmp = tempfile.mkdtemp()
    try:
        cache = os.path.join(tmp, "cache.json")
        with open(cache, "w") as fh:
            fh.write("{ broken")
        c = cat.load_catalog(cache_path=cache, factory_path=os.path.join(tmp, "none.json"))
        assert c["meta"]["source"] == "fallback"
    finally:
        shutil.rmtree(tmp)


# ---- P2: 扫码 ----
def test_qr_channels_from_catalog():
    chans = {c.id: c for c in _build_from_fixtures()["channels"]}
    qr_ids = sorted(c.id for c in chans.values() if c.supports_qr)
    assert "whatsapp" in qr_ids and "openclaw-weixin" in qr_ids
    assert "openclaw-zaloclawbot" in qr_ids and "yuanbao" in qr_ids
    assert "slack" not in qr_ids and "wecom" not in qr_ids


def test_orchestrator_login_cmd():
    assert orch.build_login_cmd("whatsapp") == ["channels", "login", "--channel", "whatsapp"]
    assert orch.build_login_cmd("whatsapp", account="a1") == [
        "channels", "login", "--channel", "whatsapp", "--account", "a1"]


def test_orchestrator_handoff_path():
    assert orch.handoff_path("whatsapp").endswith("openclaw-oneclick-whatsapp.json")


def test_orchestrator_read_handoff_missing_or_broken():
    assert orch.read_handoff("/nonexistent/nope.json") is None
    tmp = tempfile.mkdtemp()
    try:
        p = os.path.join(tmp, "half.json")
        with open(p, "w") as fh:
            fh.write('{"qr_ascii": "half writ')
        assert orch.read_handoff(p) is None
    finally:
        shutil.rmtree(tmp)


# ---- P3: 诊断与闭环 ----
def test_diag_validate_ok():
    res = diag.check_config_valid(runner=lambda cmd, timeout=30: (0, "ok"))
    assert res["status"] == "ok"


def test_diag_validate_reports_reason():
    res = diag.check_config_valid(runner=lambda cmd, timeout=30: (1, "channels.wecom: required"))
    assert res["status"] == "fail"
    assert "channels.wecom" in res["detail"]


def test_diag_gateway_probe_unreachable():
    res = diag.check_gateway_probe(runner=lambda cmd, timeout=30: (1, "connection refused"))
    assert res["status"] == "fail"


def test_verify_and_start_stops_at_invalid_config():
    """配置非法时不得继续起网关 —— 否则错误被网关启动失败掩盖。"""
    steps = []

    def fake(cmd, timeout=30):
        steps.append(" ".join(cmd[:2]))
        if cmd[:2] == ["config", "validate"]:
            return 1, "models.providers.glm: unknown"
        return 0, ""

    result = orch.verify_and_start(runner=fake)
    assert result["ok"] is False
    assert result["failed_step"] == "config_validate"
    assert "gateway start" not in steps


def test_verify_and_start_happy_path_order():
    steps = []

    def fake(cmd, timeout=30):
        steps.append(" ".join(cmd[:2]))
        return 0, "ok"

    result = orch.verify_and_start(runner=fake)
    assert result["ok"] is True
    assert steps == ["config validate", "gateway start", "gateway probe"]


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
