import json, os
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAT = os.path.join(HERE, "apps-catalog.json")
_APPS = json.load(open(CAT))["apps"]

_VARIANT_FIELDS = ("install", "detect", "remove")

def test_every_app_has_origin_and_rank():
    bad = [a["id"] for a in _APPS if a.get("origin") not in ("cn", "intl", "global")
           or not isinstance(a.get("rank"), int)]
    assert bad == [], f"缺 origin/rank 或类型错: {bad}"

def test_variants_are_wellformed():
    for a in _APPS:
        vs = a.get("variants")
        if not vs:
            continue
        assert set(vs) <= {"cn", "intl"}, f"{a['id']} 变体键非法: {set(vs)}"
        assert vs, f"{a['id']} variants 为空"
        for region, v in vs.items():
            for f in _VARIANT_FIELDS:
                assert v.get(f), f"{a['id']}.{region} 缺 {f}"
            assert v.get("origin") in ("cn", "intl", "global"), f"{a['id']}.{region} origin 非法"

def test_deb_user_apps_use_run_sh_launch():
    for a in _APPS:
        # 顶层或变体里任何 deb-user 都应有 run.sh 启动 + Applications 目录 detect
        pools = [a] + list((a.get("variants") or {}).values())
        for v in pools:
            if v.get("kind") == "deb-user":
                assert "run.sh" in v.get("launch", ""), f"{a['id']} deb-user launch 应指向 run.sh"
                assert "Applications" in v.get("detect", ""), f"{a['id']} deb-user detect 应查 Applications 目录"

def test_new_domestic_apps_present():
    ids = {a["id"] for a in _APPS}
    for want in ("qq", "todesk", "motrix", "codebuddy", "qoder", "trae", "lingma"):
        assert want in ids, f"缺国产新应用: {want}"
    # wechat/wpsoffice 应已变体化
    by = {a["id"]: a for a in _APPS}
    assert "cn" in by["wechat"]["variants"] and "intl" in by["wechat"]["variants"]
    assert by["wechat"]["variants"]["cn"]["kind"] == "deb-user"
