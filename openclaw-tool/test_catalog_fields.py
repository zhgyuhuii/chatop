# openclaw-tool/test_catalog_fields.py
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import openclaw_catalog as oc

SCHEMA = json.dumps({"properties": {"channels": {"properties": {
    "telegram": {"properties": {
        "botToken": {"type": "string", "description": "机器人 Token"},
        "silent": {"type": "boolean", "default": False},
        "mode": {"type": "string", "enum": ["poll", "webhook"]}}},
    "twitch": {"properties": {}},
}}}})

def test_parse_channel_fields_maps_types_and_secret():
    fields = oc.parse_channel_fields(SCHEMA)
    tg = {f["name"]: f for f in fields["telegram"]}
    assert tg["botToken"]["key"] == "channels.telegram.botToken"
    assert tg["botToken"]["kind"] == "secret" and tg["botToken"]["secret"] is True
    assert tg["botToken"]["help"] == "机器人 Token"
    assert tg["silent"]["kind"] == "bool"
    assert tg["mode"]["kind"] == "select" and tg["mode"]["options"] == ["poll", "webhook"]
    assert fields["twitch"] == []

def test_parse_channel_fields_bad_json():
    assert oc.parse_channel_fields("not json") == {}

def test_build_and_roundtrip_channel_fields(tmp_path):
    cat = oc.build_catalog(
        channels_json=json.dumps({"chat": {"telegram": {"accounts": [], "installed": True, "origin": "configured"}}}),
        schema_json=SCHEMA, catalog_js="", models_json="")
    assert cat["channel_fields"]["telegram"][0]["key"].startswith("channels.telegram.")
    p = str(tmp_path / "cat.json")
    oc.save_catalog(p, cat)
    loaded = oc.load_catalog(cache_path=p, factory_path="/nonexistent")
    assert "channels.telegram.botToken" in {
        f["key"] for f in loaded["channel_fields"]["telegram"]}
