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
