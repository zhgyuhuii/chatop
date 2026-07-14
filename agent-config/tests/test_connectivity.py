from agentconfig.connectivity import probes
from agentconfig.core.types import LEVEL_OK, LEVEL_ERROR, LEVEL_WARN


def test_check_unknown_channel_falls_back_to_config_completeness():
    # 未注册探针的通道 → 回落：有配置内容判 OK/warn，不真联网
    d = probes.check("some-unknown-channel", {"enabled": True, "token": "x"})
    assert d.level in (LEVEL_OK, LEVEL_WARN)
    assert d.id.startswith("conn:")


def test_check_unknown_channel_empty_config_warns():
    d = probes.check("some-unknown-channel", {})
    assert d.level == LEVEL_WARN


def test_telegram_probe_ok(monkeypatch):
    monkeypatch.setattr(probes, "_http_json",
                        lambda *a, **k: (200, {"ok": True, "result": {"username": "mybot"}}, None))
    d = probes.check("telegram", {"botToken": "123:abc"})
    assert d.level == LEVEL_OK and "mybot" in d.message


def test_telegram_probe_bad_token(monkeypatch):
    monkeypatch.setattr(probes, "_http_json",
                        lambda *a, **k: (401, {"ok": False, "description": "Unauthorized"}, "HTTP 401"))
    d = probes.check("telegram", {"botToken": "bad"})
    assert d.level == LEVEL_ERROR


def test_telegram_probe_missing_token():
    d = probes.check("telegram", {})
    assert d.level == LEVEL_WARN  # 没 token 不发网


def test_telegram_probe_does_not_leak_token(monkeypatch):
    monkeypatch.setattr(probes, "_http_json",
                        lambda *a, **k: (401, {"ok": False, "description": "Unauthorized"}, "HTTP 401"))
    d = probes.check("telegram", {"botToken": "SECRET123:abc"})
    assert "SECRET123" not in d.message


def test_discord_probe_ok(monkeypatch):
    monkeypatch.setattr(probes, "_http_json",
                        lambda *a, **k: (200, {"username": "dbot", "id": "1"}, None))
    d = probes.check("discord", {"botToken": "tok"})
    assert d.level == LEVEL_OK and "dbot" in d.message


def test_slack_probe_ok(monkeypatch):
    monkeypatch.setattr(probes, "_http_json",
                        lambda *a, **k: (200, {"ok": True, "team": "T"}, None))
    d = probes.check("slack", {"botToken": "xoxb"})
    assert d.level == LEVEL_OK
