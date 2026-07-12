# -*- coding: utf-8 -*-
from agentconfig.tutorials import loader


def test_all_channels_have_tutorial():
    ids = loader.channel_ids("openclaw")
    # 至少覆盖 testdata 里的全部通道
    assert len(ids) >= 27
    for cid in ["wecom", "openclaw-weixin", "telegram", "feishu", "whatsapp"]:
        assert cid in ids


def test_detailed_tutorial_shape():
    t = loader.get("openclaw", "wecom")
    assert t["source"] == "baked"
    assert t["auth"] == "token"
    assert t["steps"] and len(t["steps"]) >= 3
    assert t["credential_fields"]
    assert t["apply_url"]


def test_qr_tutorial():
    t = loader.get("openclaw", "openclaw-weixin")
    assert t["auth"] == "qr"
    assert any("扫" in s for s in t["steps"])


def test_missing_channel_generic_fallback():
    t = loader.get("openclaw", "some-unknown-channel", auth="qr")
    assert t["source"] == "generic"
    assert t["steps"]
    assert t["docs_url"].endswith("some-unknown-channel")
