# openclaw-tool/test_field_overrides.py
import copy
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog_overrides as ov

def test_merge_labels_and_marks_primary():
    fields = [
        {"key": "channels.telegram.name", "name": "name", "label": "name",
         "kind": "text", "secret": False, "advanced": True},
        {"key": "channels.telegram.botToken", "name": "botToken", "label": "botToken",
         "kind": "secret", "secret": True, "advanced": False},
    ]
    saved = copy.deepcopy(ov.CHANNEL_FIELD_OVERRIDES)
    try:
        ov.CHANNEL_FIELD_OVERRIDES.setdefault("telegram", {})["channels.telegram.botToken"] = {
            "label": "Bot Token", "help": "找 @BotFather 拿", "order": 0,
            "apply_url": "https://t.me/BotFather"}
        out = ov.merge_field_overrides("telegram", [dict(f) for f in fields])
        bt = next(f for f in out if f["name"] == "botToken")
        assert bt["label"] == "Bot Token" and bt["advanced"] is False
        assert bt["apply_url"] == "https://t.me/BotFather"
        nm = next(f for f in out if f["name"] == "name")
        assert nm["advanced"] is True
        assert out.index(bt) < out.index(nm)
    finally:
        ov.CHANNEL_FIELD_OVERRIDES.clear()
        ov.CHANNEL_FIELD_OVERRIDES.update(saved)

def test_merge_override_promotes_non_secret_to_primary():
    fields = [{"key": "channels.matrix.homeserver", "name": "homeserver",
               "label": "homeserver", "kind": "text", "secret": False, "advanced": True}]
    saved = copy.deepcopy(ov.CHANNEL_FIELD_OVERRIDES)
    try:
        ov.CHANNEL_FIELD_OVERRIDES.setdefault("matrix", {})["channels.matrix.homeserver"] = {
            "label": "Homeserver 地址", "order": 0}
        out = ov.merge_field_overrides("matrix", [dict(f) for f in fields])
        assert out[0]["advanced"] is False and out[0]["label"] == "Homeserver 地址"
    finally:
        ov.CHANNEL_FIELD_OVERRIDES.clear()
        ov.CHANNEL_FIELD_OVERRIDES.update(saved)
