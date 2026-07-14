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
