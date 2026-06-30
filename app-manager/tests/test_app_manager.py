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
