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
