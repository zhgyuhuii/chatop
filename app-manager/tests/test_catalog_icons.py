import json, os, re
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAT = os.path.join(HERE, "apps-catalog.json")
ICONS = os.path.join(HERE, "icons")
FALLBACK = os.path.join(HERE, "apps-icon.svg")

# 卡片底色见 novnc-src/app/styles/base.css: .chatop_app_card / body.chatop-theme-light .chatop_app_card
_GRADIENT = re.compile(r'fill\s*=\s*["\']url\(|stop-color|linearGradient|radialGradient|<image')
_COLOR = re.compile(r'(?:fill|stroke|stop-color)\s*[:=]\s*["\']?\s*(#[0-9a-fA-F]{3,8}|white|black|currentColor)')
_WHITE = {"#fff", "#ffffff", "white"}
_BLACK = {"#000", "#000000", "black"}


def _is_invisible_on_some_theme(svg: str) -> bool:
    """纯白图标在浅色卡片上隐形；纯黑/无 fill 的在深色卡片(默认主题)上隐形。"""
    if _GRADIENT.search(svg):
        return False
    toks = {t.lower() for t in _COLOR.findall(svg)}
    if toks - _WHITE - _BLACK - {"currentcolor"}:
        return False  # 有真彩色
    return True  # 无 fill、或只有纯白/纯黑

def test_no_remote_icons_in_catalog():
    d = json.load(open(CAT))
    remote = [a["id"] for a in d["apps"] if str(a.get("icon","")).startswith("http")]
    assert remote == [], f"仍有远程图标(离线会裂): {remote}"

def test_every_icon_file_exists_locally():
    d = json.load(open(CAT))
    missing = [a["icon"] for a in d["apps"]
               if a.get("icon") and not os.path.isfile(os.path.join(ICONS, a["icon"]))]
    assert missing == [], f"catalog 引用了不存在的本地图标: {missing}"


def test_no_app_ships_the_placeholder_as_its_icon():
    placeholder = open(FALLBACK, encoding="utf-8").read()
    d = json.load(open(CAT))
    same = []
    for a in d["apps"]:
        p = os.path.join(ICONS, a.get("icon", ""))
        if os.path.isfile(p) and open(p, encoding="utf-8", errors="replace").read() == placeholder:
            same.append(a["id"])
    assert same == [], f"这些应用只有占位符、没有真图标: {same}"


def test_no_icon_is_invisible_on_either_theme():
    bad = []
    for f in sorted(os.listdir(ICONS)):
        if not f.endswith(".svg"):
            continue
        svg = open(os.path.join(ICONS, f), encoding="utf-8", errors="replace").read()
        if _is_invisible_on_some_theme(svg):
            bad.append(f)
    assert bad == [], f"这些图标只有纯白/纯黑/无 fill，某个主题下会隐形: {bad}"
