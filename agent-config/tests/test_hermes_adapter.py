# -*- coding: utf-8 -*-
import json
import os

from agentconfig.adapters.hermes_adapter import HermesAdapter


def test_status_unconfigured(tmp_path):
    a = HermesAdapter(home=str(tmp_path))
    st = a.status()
    assert st.configured is False


def test_apply_and_read_redacts(tmp_path):
    a = HermesAdapter(home=str(tmp_path))
    res = a.apply({"api_key": "sk-verysecret", "model": "hermes-4", "ignored": "x"})
    assert res.ok
    raw = json.load(open(os.path.join(str(tmp_path), ".hermes/config.json")))
    assert raw["api_key"] == "sk-verysecret" and "ignored" not in raw  # 只保留白名单字段
    red = a.read_config(redact=True)
    assert red["api_key"].startswith("***") and red["model"] == "hermes-4"


def test_describe_has_fields(tmp_path):
    a = HermesAdapter(home=str(tmp_path))
    d = a.describe()
    keys = {f.key for g in d.groups for f in g.fields}
    assert {"api_key", "model"} <= keys


def test_yaml_present_degrades(tmp_path):
    cfgdir = tmp_path / ".hermes"
    cfgdir.mkdir()
    (cfgdir / "config.yaml").write_text("api_key: x\n")
    a = HermesAdapter(home=str(tmp_path))
    cfg = a.read_config()
    assert "_load_error" in cfg
    diags = a.health_check()
    assert any(d.id == "config_broken" for d in diags)


def test_health_configured(tmp_path):
    a = HermesAdapter(home=str(tmp_path))
    a.apply({"api_key": "k", "model": "hermes-4"})
    diags = a.health_check()
    # 未装 hermes 会有 not_installed，但不应有 no_key/no_model
    ids = {d.id for d in diags}
    assert "no_key" not in ids and "no_model" not in ids
