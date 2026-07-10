import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import app_manager as am

# 合成 catalog：一个国产(cn)、一个境外(intl)、一个带 cn/intl 双变体
CATALOG = {"version": 1, "apps": [
    {"id": "claude", "name": "Claude", "category": "ai-cli", "kind": "cli-npm",
     "icon": "c.png", "description": "d", "origin": "intl", "rank": 50,
     "install": "npm i -g claude", "remove": "r", "detect": "command -v claude",
     "needs": [], "homepage": "h", "notes": "n"},
    {"id": "qwen", "name": "Qwen", "category": "ai-cli", "kind": "cli-npm",
     "icon": "q.png", "description": "d", "origin": "cn", "rank": 85,
     "install": "npm i -g qwen", "remove": "r", "detect": "command -v qwen",
     "needs": [], "homepage": "h", "notes": "n"},
    {"id": "wps", "name": "WPS", "category": "office", "icon": "w.png",
     "description": "d", "rank": 70, "needs": [], "homepage": "h", "notes": "n",
     "variants": {
        "cn":   {"origin": "cn", "kind": "deb-user", "install": "install-wps-cn",
                 "detect": "test -d ~/Applications/wps", "remove": "rm-wps", "launch": "run-wps-cn"},
        "intl": {"origin": "intl", "kind": "proot-app", "install": "proot-apps install wpsoffice",
                 "detect": "test -d intl", "remove": "proot-apps remove wpsoffice", "launch": "proot-apps run wpsoffice"},
     }},
]}

def _mgr(tmp):
    p = os.path.join(tmp, "c.json"); open(p, "w").write(json.dumps(CATALOG))
    return am.AppManager(p)

def test_region_for_lang_maps_cn_and_intl():
    assert am._region_for_lang("zh_CN") == "cn"
    assert am._region_for_lang("zh_TW") == "cn"
    assert am._region_for_lang("en") == "intl"
    assert am._region_for_lang("ja") == "intl"
    assert am._region_for_lang(None) == "cn"

def test_variant_flattened_by_lang():
    with tempfile.TemporaryDirectory() as t:
        m = _mgr(t)
        zh = {a["id"]: a for a in m.public_catalog("zh_CN")["apps"]}["wps"]
        en = {a["id"]: a for a in m.public_catalog("en")["apps"]}["wps"]
        assert zh["origin"] == "cn" and zh["kind"] == "deb-user"
        assert en["origin"] == "intl" and en["kind"] == "proot-app"
        # variants 键不应下发给前端
        assert "variants" not in zh and "variants" not in en

def test_domestic_first_ordering_under_zh():
    with tempfile.TemporaryDirectory() as t:
        ids = [a["id"] for a in _mgr(t).public_catalog("zh_CN")["apps"]]
        # rank: qwen85 > wps70 > claude50 → 国产在前
        assert ids == ["qwen", "wps", "claude"]

def test_cn_gets_badge():
    with tempfile.TemporaryDirectory() as t:
        by = {a["id"]: a for a in _mgr(t).public_catalog("zh_CN")["apps"]}
        assert by["qwen"].get("badge") == "国产"
        assert "badge" not in by["claude"]

def test_install_command_picks_variant_by_lang():
    with tempfile.TemporaryDirectory() as t:
        m = _mgr(t)
        assert m.command_for("wps", "install", "zh_CN") == "install-wps-cn"
        assert m.command_for("wps", "install", "en") == "proot-apps install wpsoffice"

def test_launch_uses_variant_by_lang():
    with tempfile.TemporaryDirectory() as t:
        m = _mgr(t)
        assert m.launch_cmd("wps", "zh_CN") == "run-wps-cn"
        assert m.launch_cmd("wps", "en") == "proot-apps run wpsoffice"
