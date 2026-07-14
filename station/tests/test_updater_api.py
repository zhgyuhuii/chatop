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
    services_dir = tmp_path / "services"
    monkeypatch.setenv("CHATOP_SERVICES_DIR", str(services_dir))
    monkeypatch.setenv("CHATOP_FACTORY_DIR", str(tmp_path / "factory"))
    # station 有一个活的 current 软链 -> path 必须按调用期的 CHATOP_SERVICES_DIR
    # 解析，而不是 services.py 里 import 期钉死的默认目录，否则 path/active 会分家。
    ver_dir = services_dir / "station" / "1.6.0"
    ver_dir.mkdir(parents=True)
    (services_dir / "station" / "current").symlink_to("1.6.0")
    c = _client(tmp_path)
    r = c.get("/dashboard/api/updater/versions")
    assert r.status_code == 200
    body = r.json()
    assert "services" in body
    names = {s["name"] for s in body["services"]}
    assert {"station", "agent-config", "dashboard-web", "openclaw-tool"} <= names
    station = next(s for s in body["services"] if s["name"] == "station")
    assert station["active"] == "1.6.0"
    assert str(services_dir) in station["path"]


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


def _apply_env(tmp_path, monkeypatch, key):
    monkeypatch.setenv("CHATOP_SERVICES_DIR", str(tmp_path / "services"))
    monkeypatch.setenv("CHATOP_FACTORY_DIR", str(tmp_path / "factory"))
    monkeypatch.setenv("CHATOP_UPDATER_INBOX", str(tmp_path / "inbox"))
    monkeypatch.setenv("CHATOP_LICENSE_KEYS_FILE", str(tmp_path / "keys.json"))
    (tmp_path / "keys.json").write_text(json.dumps(
        {"active_key_id": 1, "hmac_keys": {"1": key.hex()}}))


def test_apply_rejects_unknown_service(tmp_path, monkeypatch):
    key = b"k" * 32
    _apply_env(tmp_path, monkeypatch, key)
    c = _client(tmp_path)
    r = c.post("/dashboard/api/updater/apply",
               json={"name": "../../etc", "version": "1.0", "health": "skip"})
    assert r.status_code == 400
    # 未逃出 services_dir：没有为该恶意名创建任何目录
    assert not (tmp_path / "services").exists() or \
        list((tmp_path / "services").iterdir()) == []


def test_apply_missing_bundle_404(tmp_path, monkeypatch):
    key = b"k" * 32
    _apply_env(tmp_path, monkeypatch, key)
    (tmp_path / "inbox").mkdir(parents=True, exist_ok=True)
    c = _client(tmp_path)
    r = c.post("/dashboard/api/updater/apply",
               json={"name": "agent-config", "version": "9.9.9", "health": "skip"})
    assert r.status_code == 404


def test_apply_manifest_mismatch_400(tmp_path, monkeypatch):
    key = b"k" * 32
    _apply_env(tmp_path, monkeypatch, key)
    inbox = tmp_path / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    # 构造一个合法 bundle，但 manifest 的 name 指向另一个服务名
    payload = inbox / "pl1.6.0"; payload.mkdir()
    (payload / "v.txt").write_text("1.6.0")
    tar = inbox / "agent-config-1.6.0.tar.gz"
    with tarfile.open(tar, "w:gz") as tf:
        tf.add(payload / "v.txt", arcname="v.txt")
    sha = hashlib.sha256(tar.read_bytes()).hexdigest()
    sig = hmac.new(key, sha.encode(), hashlib.sha256).hexdigest()
    (inbox / "agent-config-1.6.0.json").write_text(json.dumps(
        {"name": "dashboard-web", "version": "1.6.0", "sha256": sha, "sig": sig,
         "min_base": "1.5.0", "needs_venv": False}))
    c = _client(tmp_path)
    r = c.post("/dashboard/api/updater/apply",
               json={"name": "agent-config", "version": "1.6.0", "health": "skip"})
    assert r.status_code == 400


def test_rollback_endpoint(tmp_path, monkeypatch):
    key = b"k" * 32
    _apply_env(tmp_path, monkeypatch, key)
    _make_inbox_bundle(tmp_path / "inbox", "agent-config", "1.6.0", key)
    _make_inbox_bundle(tmp_path / "inbox", "agent-config", "1.7.0", key)
    c = _client(tmp_path)
    for ver in ("1.6.0", "1.7.0"):
        r = c.post("/dashboard/api/updater/apply",
                   json={"name": "agent-config", "version": ver, "health": "skip"})
        assert r.status_code == 200 and r.json()["ok"] is True
    cur = tmp_path / "services" / "agent-config" / "current"
    assert (cur / "v.txt").read_text() == "1.7.0"
    # rollback：回退到上一个版本（更低排序的 1.6.0）
    r = c.post("/dashboard/api/updater/rollback", json={"name": "agent-config"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert (cur / "v.txt").read_text() == "1.6.0"
