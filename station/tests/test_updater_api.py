from fastapi.testclient import TestClient
from station.api import create_app
from station.events import EventHub
from station.tasks.store import TaskStore
from station.tasks.dispatcher import Dispatcher


def _client(tmp_path):
    store = TaskStore(tmp_path / "s.db")
    hub = EventHub()
    disp = Dispatcher(store, hub, nickname="t")
    app = create_app(store, hub, disp)
    return TestClient(app)


def test_versions_endpoint_lists_services(tmp_path, monkeypatch):
    monkeypatch.setenv("CHATOP_SERVICES_DIR", str(tmp_path / "services"))
    monkeypatch.setenv("CHATOP_FACTORY_DIR", str(tmp_path / "factory"))
    c = _client(tmp_path)
    r = c.get("/dashboard/api/updater/versions")
    assert r.status_code == 200
    body = r.json()
    assert "services" in body
    names = {s["name"] for s in body["services"]}
    assert {"station", "agent-config", "dashboard-web", "openclaw-tool"} <= names


import hashlib, hmac, json, tarfile
from pathlib import Path


def _make_inbox_bundle(inbox: Path, name: str, ver: str, key: bytes):
    inbox.mkdir(parents=True, exist_ok=True)
    payload = inbox / f"pl{ver}"; payload.mkdir()
    (payload / "v.txt").write_text(ver)
    tar = inbox / f"{name}-{ver}.tar.gz"
    with tarfile.open(tar, "w:gz") as tf:
        tf.add(payload / "v.txt", arcname="v.txt")
    sha = hashlib.sha256(tar.read_bytes()).hexdigest()
    sig = hmac.new(key, sha.encode(), hashlib.sha256).hexdigest()
    (inbox / f"{name}-{ver}.json").write_text(json.dumps(
        {"name": name, "version": ver, "sha256": sha, "sig": sig,
         "min_base": "1.5.0", "needs_venv": False}))
    return tar


def test_apply_endpoint_applies_bundle(tmp_path, monkeypatch):
    key = b"k" * 32
    monkeypatch.setenv("CHATOP_SERVICES_DIR", str(tmp_path / "services"))
    monkeypatch.setenv("CHATOP_FACTORY_DIR", str(tmp_path / "factory"))
    monkeypatch.setenv("CHATOP_UPDATER_INBOX", str(tmp_path / "inbox"))
    monkeypatch.setenv("CHATOP_LICENSE_KEYS_FILE", str(tmp_path / "keys.json"))
    (tmp_path / "keys.json").write_text(json.dumps(
        {"active_key_id": 1, "hmac_keys": {"1": key.hex()}}))
    _make_inbox_bundle(tmp_path / "inbox", "agent-config", "1.6.0", key)
    c = _client(tmp_path)
    r = c.post("/dashboard/api/updater/apply",
               json={"name": "agent-config", "version": "1.6.0", "health": "skip"})
    assert r.status_code == 200 and r.json()["ok"] is True
    cur = tmp_path / "services" / "agent-config" / "current"
    assert (cur / "v.txt").read_text() == "1.6.0"
