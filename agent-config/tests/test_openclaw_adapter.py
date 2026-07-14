# -*- coding: utf-8 -*-
import json
import os

import pytest

from agentconfig.adapters.openclaw_adapter import OpenClawAdapter
from agentconfig.core import types
from conftest import build_catalog_snapshot


@pytest.fixture
def home(tmp_path):
    build_catalog_snapshot(str(tmp_path))
    return str(tmp_path)


def test_describe_lists_channels(home):
    a = OpenClawAdapter(home=home)
    d = a.describe()
    gids = {g.id for g in d.groups}
    assert {"model", "channels", "gateway"} <= gids
    ch_group = next(g for g in d.groups if g.id == "channels")
    ids = {c.id for c in ch_group.channels}
    # testdata 里应含这些通道
    assert "wecom" in ids and "telegram" in ids and "openclaw-weixin" in ids


def test_describe_backfills_fallbacks(home):
    a = OpenClawAdapter(home=home)
    a.apply({"agents": {"defaults": {"model": {
        "primary": "deepseek/deepseek-chat",
        "fallbacks": ["a/x", "a/y"]}}}})
    d = a.describe()
    mg = next(g for g in d.groups if g.id == "model")
    fb = next(f for f in mg.fields if f.key == "agents.defaults.model.fallbacks")
    assert fb.value == ["a/x", "a/y"]


def test_auth_flow_kinds(home):
    a = OpenClawAdapter(home=home)
    assert a.auth_flow("openclaw-weixin").kind == types.AUTH_QR
    assert a.auth_flow("whatsapp").kind == types.AUTH_QR
    tg = a.auth_flow("telegram")
    assert tg.kind == types.AUTH_TOKEN and tg.fields
    # wecom 在 testdata schema 里是空壳（channels.wecom 为 null），无显式字段可解析——
    # 走 free_kv（此前手写 _TOKEN_FIELDS 硬编码了 3 个字段，schema 驱动后如实反映真源）。
    wecom = a.auth_flow("wecom")
    assert wecom.kind == types.AUTH_TOKEN
    assert wecom.fields == [] and wecom.free_kv is True
    # builtin
    assert a.auth_flow("imessage").kind == types.AUTH_BUILTIN


def test_qr_flow_has_cmd(home):
    a = OpenClawAdapter(home=home)
    flow = a.auth_flow("openclaw-weixin")
    assert flow.cmd and flow.cmd[0] == "openclaw"


def test_apply_writes_and_sanitizes(home):
    a = OpenClawAdapter(home=home)
    res = a.apply({"agents": {"defaults": {"model": {"primary": "deepseek/deepseek-chat"}}}})
    assert res.ok
    cfg = json.load(open(os.path.join(home, ".openclaw/openclaw.json"), encoding="utf-8"))
    assert cfg["agents"]["defaults"]["model"]["primary"] == "deepseek/deepseek-chat"


def test_apply_removes_bogus_channel(home):
    a = OpenClawAdapter(home=home)
    # 伪通道应被 sanitize 移除
    res = a.apply({"channels": {"webchat": {"enabled": True}}})
    assert any("webchat" in r for r in res.removed)


def test_apply_preserves_builtin_bare_enable(home):
    # builtin 通道（imessage）只填 enabled:true 也应真正启用，不被 sanitize 剥掉。
    a = OpenClawAdapter(home=home)
    res = a.apply({"channels": {"imessage": {"enabled": True}}})
    assert "channels.imessage" not in res.removed
    cfg = a.read_config(redact=False)
    assert cfg["channels"]["imessage"]["enabled"] is True


def test_builtin_enable_survives_later_unrelated_apply(home):
    # 启用 imessage 后，再执行一次无关的 apply（配模型），imessage 不应被剥回去。
    a = OpenClawAdapter(home=home)
    a.apply({"channels": {"imessage": {"enabled": True}}})
    a.apply({"agents": {"defaults": {"model": {"primary": "deepseek/deepseek-chat"}}}})
    cfg = a.read_config(redact=False)
    assert (cfg.get("channels") or {}).get("imessage", {}).get("enabled") is True


def test_apply_still_strips_bare_enable_for_token_channel(home):
    # token 通道（telegram）只有 enabled、无凭据仍应被剥（缺字段会让网关校验失败）。
    a = OpenClawAdapter(home=home)
    res = a.apply({"channels": {"telegram": {"enabled": True}}})
    assert "channels.telegram" in res.removed
    assert "telegram" not in (a.read_config(redact=False).get("channels") or {})


def test_read_config_redacts_secret(home):
    a = OpenClawAdapter(home=home)
    a.apply({"channels": {"discord": {"enabled": True, "token": "supersecrettoken"}}})
    red = a.read_config(redact=True)
    tok = red["channels"]["discord"]["token"]
    assert tok.startswith("***") and "supersecret" not in tok


def test_health_check_flags_missing_model(home):
    a = OpenClawAdapter(home=home)
    diags = a.health_check()
    assert any(d.id == "no_model" for d in diags)


def _fake_qr_block():
    # 一个足够大的方块二维码 ASCII（parse_ascii_qr 认 █/半块；这里用满块）。
    row = "█" * 21
    return "\n".join(row for _ in range(21))


def test_run_flow_qr_ready_when_log_has_code(home):
    block = _fake_qr_block()

    def fake_spawn(script, log_path):
        import os
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "w", encoding="utf-8") as fh:
            fh.write("扫码登录\n" + block + "\n")

    a = OpenClawAdapter(home=home, flow_spawn=fake_spawn,
                        qr_poll_tries=3, qr_poll_interval=0, sleep=lambda s: None)
    events = []
    a.run_flow("openclaw-weixin", {}, lambda e: events.append(e.to_dict()))
    types_ = [e["type"] for e in events]
    assert "flow:terminal" in types_
    assert any(t == "flow:qr_ready" for t in types_)


def test_run_flow_qr_missing_when_no_code(home):
    a = OpenClawAdapter(home=home, flow_spawn=lambda s, l: None,
                        qr_poll_tries=2, qr_poll_interval=0, sleep=lambda s: None)
    events = []
    a.run_flow("openclaw-weixin", {}, lambda e: events.append(e.to_dict()))
    assert events[-1]["type"] == "flow:qr_missing"


def test_run_flow_rejects_injection_channel(home):
    # 带 shell 元字符的 channel 必须在 spawn 前被拒，绝不进入 bash 脚本拼接。
    spawned = []
    a = OpenClawAdapter(home=home, flow_spawn=lambda s, l: spawned.append(s),
                        qr_poll_tries=1, qr_poll_interval=0, sleep=lambda s: None)
    events = []
    a.run_flow("openclaw-weixin; rm -rf ~", {}, lambda e: events.append(e.to_dict()))
    assert spawned == []                       # 从未 spawn
    assert events and events[-1]["type"] == "flow:error"


def test_run_flow_noop_for_token(home):
    a = OpenClawAdapter(home=home)
    events = []
    a.run_flow("telegram", {}, lambda e: events.append(e.to_dict()))
    assert events and events[0]["type"] == "flow_noop"


def test_auth_flow_fields_from_schema_with_primary(home):
    a = OpenClawAdapter(home=home)
    af = a.auth_flow("telegram")
    keys = [f.key for f in af.fields]
    assert "channels.telegram.botToken" in keys
    bt = next(f for f in af.fields if f.key == "channels.telegram.botToken")
    assert bt.secret is True and bt.advanced is False and bt.label == "Bot Token"
    assert sum(1 for f in af.fields if f.advanced) >= 10


def test_auth_flow_multifield_channel(home):
    a = OpenClawAdapter(home=home)
    af = a.auth_flow("matrix")
    assert "channels.matrix.accessToken" in {f.key for f in af.fields}


def test_auth_flow_empty_schema_is_free_kv(home):
    a = OpenClawAdapter(home=home)
    af = a.auth_flow("twitch")
    assert af.free_kv is True and af.fields == []


def test_check_connectivity_reads_channel_cfg(home, monkeypatch):
    from agentconfig.connectivity import probes
    a = OpenClawAdapter(home=home)
    a.apply({"channels": {"telegram": {"enabled": True, "botToken": "123:abc"}}})
    monkeypatch.setattr(probes, "_http_json",
                        lambda *a2, **k: (200, {"ok": True, "result": {"username": "b"}}, None))
    d = a.check_connectivity("telegram")
    assert d.level == types.LEVEL_OK


def test_check_connectivity_unconfigured_channel_warns(home):
    a = OpenClawAdapter(home=home)
    d = a.check_connectivity("telegram")
    assert d.level == types.LEVEL_WARN  # 没配 → probe 判 empty
