import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import app_manager as am

CATALOG = {"version":1,"apps":[
  {"id":"aider","name":"Aider","category":"ai-cli","kind":"cli-pip","icon":"aider.png",
   "description":"d","install":"pipx install aider-chat","remove":"pipx uninstall aider-chat",
   "detect":"command -v aider","needs":[],"homepage":"h","notes":"n"}]}

def _mgr(tmp_path):
    p = os.path.join(tmp_path, "c.json"); open(p,"w").write(json.dumps(CATALOG))
    return am.AppManager(p)

def test_public_catalog_strips_commands():
    with tempfile.TemporaryDirectory() as t:
        pub = _mgr(t).public_catalog()
        app = pub["apps"][0]
        assert app["id"] == "aider" and "icon" in app and "description" in app
        assert "install" not in app and "remove" not in app and "detect" not in app

def test_install_rejects_unknown_id():
    with tempfile.TemporaryDirectory() as t:
        try:
            _mgr(t).command_for("nope", "install"); assert False
        except KeyError:
            pass

def test_command_for_returns_predefined():
    with tempfile.TemporaryDirectory() as t:
        assert _mgr(t).command_for("aider","install") == "pipx install aider-chat"

def test_status_uses_detect():
    with tempfile.TemporaryDirectory() as t:
        m = _mgr(t)
        m._run_detect = lambda cmd: cmd == "command -v aider"
        assert m.status() == {"aider": True}

def test_groupstore_load_missing_returns_empty():
    with tempfile.TemporaryDirectory() as t:
        gs = am.GroupStore(os.path.join(t, "nope", "groups.json"))
        assert gs.load() == {"version": 1, "items": [], "pulled_out_system": []}

def test_groupstore_save_then_load_roundtrip():
    with tempfile.TemporaryDirectory() as t:
        gs = am.GroupStore(os.path.join(t, "sub", "groups.json"))
        data = {"version": 1,
                "items": [{"type": "group", "id": "g1", "name": "办公", "apps": ["wps"]}],
                "pulled_out_system": []}
        gs.save(data)
        assert gs.load() == data

def test_groupstore_load_corrupt_returns_empty():
    with tempfile.TemporaryDirectory() as t:
        p = os.path.join(t, "groups.json"); open(p, "w").write("{not json")
        assert am.GroupStore(p).load() == {"version": 1, "items": [], "pulled_out_system": []}

def _layout(items, pulled=None):
    return {"version": 1, "items": items, "pulled_out_system": pulled or []}

def _inst(key, source="user"):
    return {"key": key, "name": key, "source": source}

def test_reconcile_drops_uninstalled_apps():
    gs = am.GroupStore("/x")
    layout = _layout([{"type": "app", "key": "gone"}, {"type": "app", "key": "chrome"}])
    out = gs.reconcile(layout, [_inst("chrome")])
    keys = [i["key"] for i in out["items"] if i["type"] == "app"]
    assert keys == ["chrome"]

def test_reconcile_drops_empty_group():
    gs = am.GroupStore("/x")
    layout = _layout([{"type": "group", "id": "g1", "name": "空", "apps": ["gone"]}])
    out = gs.reconcile(layout, [_inst("chrome")])
    groups = [i for i in out["items"] if i["type"] == "group"]
    assert groups == []
    assert [i["key"] for i in out["items"] if i["type"] == "app"] == ["chrome"]

def test_reconcile_new_user_app_goes_top_level_end():
    gs = am.GroupStore("/x")
    layout = _layout([{"type": "app", "key": "chrome"}])
    out = gs.reconcile(layout, [_inst("chrome"), _inst("newapp")])
    assert [i["key"] for i in out["items"] if i["type"] == "app"] == ["chrome", "newapp"]

def test_reconcile_system_app_auto_grouped():
    gs = am.GroupStore("/x")
    out = gs.reconcile(_layout([]), [_inst("thunar", "system")])
    grp = [i for i in out["items"] if i["type"] == "group"]
    assert len(grp) == 1 and grp[0].get("auto") is True
    assert "thunar" in grp[0]["apps"]

def test_reconcile_pulled_out_system_not_regrouped():
    gs = am.GroupStore("/x")
    layout = _layout([{"type": "app", "key": "thunar"}], pulled=["thunar"])
    out = gs.reconcile(layout, [_inst("thunar", "system")])
    grp = [i for i in out["items"] if i["type"] == "group"]
    assert grp == []
    assert [i["key"] for i in out["items"] if i["type"] == "app"] == ["thunar"]

def test_reconcile_keeps_existing_group_membership():
    gs = am.GroupStore("/x")
    layout = _layout([{"type": "group", "id": "g1", "name": "办公", "apps": ["wps"]}])
    out = gs.reconcile(layout, [_inst("wps"), _inst("chrome")])
    grp = [i for i in out["items"] if i["type"] == "group"][0]
    assert grp["apps"] == ["wps"]
    assert [i["key"] for i in out["items"] if i["type"] == "app"] == ["chrome"]

def _write_desktop(d, key, exec_line):
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, key + ".desktop"), "w").write(
        "[Desktop Entry]\nType=Application\nName=%s\nExec=%s\nIcon=x\n" % (key, exec_line))

def test_uninstall_cmd_proot(monkeypatch):
    with tempfile.TemporaryDirectory() as t:
        home = os.path.join(t, "home"); appdir = os.path.join(home, ".local/share/applications")
        monkeypatch.setenv("HOME", home)
        monkeypatch.setattr(am, "APP_DIRS", [appdir])
        _write_desktop(appdir, "wechat-pa", "proot-apps run wechat")
        assert _mgr(t).uninstall_cmd("wechat-pa") == "proot-apps remove wechat"

def test_uninstall_cmd_appimage(monkeypatch):
    with tempfile.TemporaryDirectory() as t:
        home = os.path.join(t, "home"); appdir = os.path.join(home, ".local/share/applications")
        os.makedirs(os.path.join(home, "Applications", "void"))
        monkeypatch.setenv("HOME", home)
        monkeypatch.setattr(am, "APP_DIRS", [appdir])
        _write_desktop(appdir, "chatop-void", "/home/x/Applications/void/squashfs-root/AppRun")
        assert _mgr(t).uninstall_cmd("chatop-void") == \
            "bash /usr/local/lib/chatop/gui-uninstall.sh void"

def test_uninstall_cmd_system_returns_none(monkeypatch):
    with tempfile.TemporaryDirectory() as t:
        home = os.path.join(t, "home"); sysdir = os.path.join(t, "usr/share/applications")
        monkeypatch.setenv("HOME", home)
        monkeypatch.setattr(am, "APP_DIRS", [sysdir])
        _write_desktop(sysdir, "thunar", "thunar %F")
        assert _mgr(t).uninstall_cmd("thunar") is None

def test_uninstall_cmd_unknown_returns_none(monkeypatch):
    with tempfile.TemporaryDirectory() as t:
        monkeypatch.setattr(am, "APP_DIRS", [t])
        assert _mgr(t).uninstall_cmd("nope") is None

import base64 as _b64

def test_captcha_check_roundtrip():
    ans, cookie = am._captcha_new()
    assert am._captcha_check(cookie, ans)              # 原样正确
    assert am._captcha_check(cookie, ans.lower())      # 大小写不敏感
    assert am._captcha_check(cookie, " " + ans + " ")  # 去空格
    assert not am._captcha_check(cookie, "ZZZZ")        # 答案错
    assert not am._captcha_check("garbage", ans)        # cookie 非法
    assert not am._captcha_check(cookie[:-1] + ("0" if cookie[-1] != "0" else "1"), ans)  # 签名被篡改

def test_captcha_expired():
    payload = "abcd|1"  # exp=1（1970 年，必过期）
    sig = am.hmac.new(am.AUTH_TOKEN.encode(), payload.encode(), am.hashlib.sha256).hexdigest()
    cookie = _b64.urlsafe_b64encode(payload.encode()).decode() + "." + sig
    assert not am._captcha_check(cookie, "abcd")

def test_captcha_svg_well_formed():
    ans, _ = am._captcha_new()
    svg = am._captcha_svg(ans)
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")

def test_ratelimit_delays_after_threshold():
    am._LOGIN_FAILS.clear()
    ip = "1.2.3.4"
    for _ in range(am.RL_MAX):
        assert am._ratelimit_delay(ip, now=1000) == 0
        am._ratelimit_record_fail(ip, now=1000)
    assert am._ratelimit_delay(ip, now=1000) == am.RL_DELAY   # 达阈值 → 延时
    am._ratelimit_reset(ip)
    assert am._ratelimit_delay(ip, now=1000) == 0             # 成功登录清零

def test_ratelimit_window_expires():
    am._LOGIN_FAILS.clear()
    ip = "5.6.7.8"
    for _ in range(am.RL_MAX):
        am._ratelimit_record_fail(ip, now=1000)
    assert am._ratelimit_delay(ip, now=1000) == am.RL_DELAY
    assert am._ratelimit_delay(ip, now=1000 + am.RL_WINDOW + 1) == 0  # 窗口过期不再延时
