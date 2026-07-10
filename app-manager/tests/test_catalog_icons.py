import json, os
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAT = os.path.join(HERE, "apps-catalog.json")
ICONS = os.path.join(HERE, "icons")

def test_no_remote_icons_in_catalog():
    d = json.load(open(CAT))
    remote = [a["id"] for a in d["apps"] if str(a.get("icon","")).startswith("http")]
    assert remote == [], f"仍有远程图标(离线会裂): {remote}"

def test_every_icon_file_exists_locally():
    d = json.load(open(CAT))
    missing = [a["icon"] for a in d["apps"]
               if a.get("icon") and not os.path.isfile(os.path.join(ICONS, a["icon"]))]
    assert missing == [], f"catalog 引用了不存在的本地图标: {missing}"
