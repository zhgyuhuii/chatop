import os
from pathlib import Path
from station import services


def _mk(base: Path, name: str, ver: str) -> Path:
    d = base / name / ver
    d.mkdir(parents=True)
    (d / "marker.txt").write_text(ver)
    cur = base / name / "current"
    cur.symlink_to(ver)  # 相对软链
    return d


def test_resolve_prefers_volume_current(tmp_path, monkeypatch):
    vol = tmp_path / "services"
    fac = tmp_path / "factory"
    (fac / "station").mkdir(parents=True)
    (fac / "station" / "marker.txt").write_text("factory")
    _mk(vol, "station", "1.6.0")
    monkeypatch.setattr(services, "SERVICES_DIR", vol)
    monkeypatch.setattr(services, "FACTORY_DIR", fac)
    got = services.resolve("station")
    assert (got / "marker.txt").read_text() == "1.6.0"


def test_resolve_falls_back_to_factory_when_no_current(tmp_path, monkeypatch):
    vol = tmp_path / "services"
    fac = tmp_path / "factory"
    (fac / "station").mkdir(parents=True)
    (fac / "station" / "marker.txt").write_text("factory")
    monkeypatch.setattr(services, "SERVICES_DIR", vol)
    monkeypatch.setattr(services, "FACTORY_DIR", fac)
    got = services.resolve("station")
    assert (got / "marker.txt").read_text() == "factory"


def test_resolve_falls_back_when_current_dangling(tmp_path, monkeypatch):
    vol = tmp_path / "services"
    fac = tmp_path / "factory"
    (fac / "agent-config").mkdir(parents=True)
    (fac / "agent-config" / "marker.txt").write_text("factory")
    (vol / "agent-config").mkdir(parents=True)
    (vol / "agent-config" / "current").symlink_to("9.9.9")  # 指向不存在
    monkeypatch.setattr(services, "SERVICES_DIR", vol)
    monkeypatch.setattr(services, "FACTORY_DIR", fac)
    got = services.resolve("agent-config")
    assert (got / "marker.txt").read_text() == "factory"
