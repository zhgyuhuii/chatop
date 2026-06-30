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
