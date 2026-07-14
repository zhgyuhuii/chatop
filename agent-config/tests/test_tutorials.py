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


def test_all_27_channels_have_tutorial():
    from agentconfig.tutorials import _build_data as b
    data = b.build()["openclaw"]
    # 27 通道全覆盖
    assert len(data) >= 27
    for cid, e in data.items():
        assert e["steps"], f"{cid} 无步骤"
        assert e.get("docs_url"), f"{cid} 无 docs_url"


def test_longtail_channels_are_detailed_not_generic():
    from agentconfig.tutorials import _build_data as b
    longtail = ["matrix", "mattermost", "irc", "twitch", "nostr", "zalo",
                "clickclack", "nextcloud-talk", "sms", "synology-chat",
                "tlon", "zalouser", "openclaw-zaloclawbot"]
    for cid in longtail:
        assert cid in b.DETAILED, f"{cid} 仍走通用模板，未手写"
