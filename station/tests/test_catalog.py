import json

from station.probe.catalog import detect_installed, load_ai_apps

CATALOG = {"version": 1, "apps": [
    {"id": "claude-code", "name": "Claude Code", "category": "ai-cli", "detect": "command -v claude"},
    {"id": "openclaw", "name": "OpenClaw", "category": "ai-runtime", "detect": "command -v openclaw"},
    {"id": "gimp", "name": "GIMP", "category": "proot-gui", "detect": "command -v gimp"},
]}


def test_load_filters_ai_categories(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps(CATALOG))
    apps = load_ai_apps(p)
    assert [a["id"] for a in apps] == ["claude-code", "openclaw"]


def test_detect_installed_marks_flag(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps(CATALOG))
    apps = detect_installed(load_ai_apps(p), run=lambda cmd: "claude" in cmd)
    by = {a["id"]: a["installed"] for a in apps}
    assert by == {"claude-code": True, "openclaw": False}


def test_missing_catalog_returns_empty(tmp_path):
    assert load_ai_apps(tmp_path / "nope.json") == []
