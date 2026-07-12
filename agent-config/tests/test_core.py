# -*- coding: utf-8 -*-
import pytest

from agentconfig.core import registry, types


def test_types_to_dict_roundtrip():
    fs = types.FieldSpec(key="a.b", label="标签", kind=types.FIELD_SECRET, secret=True)
    d = fs.to_dict()
    assert d["key"] == "a.b" and d["secret"] is True
    af = types.AuthFlowDescriptor(kind=types.AUTH_QR, target="wecom")
    assert af.to_dict()["kind"] == "qr"
    ev = types.Event("flow:qr_ready", {"channel": "wecom"})
    assert ev.to_dict() == {"type": "flow:qr_ready", "channel": "wecom"}


def test_registry_dispatch_and_reset():
    class Dummy:
        id = "dummy"
        label = "Dummy"

    registry.register("dummy", lambda: Dummy())
    a = registry.get("dummy")
    assert a is registry.get("dummy")  # 缓存
    assert "dummy" in registry.ids()
    registry.reset()
    assert registry.get("dummy") is not a  # reset 后重建


def test_registry_unknown():
    with pytest.raises(KeyError):
        registry.get("nope-not-registered")
