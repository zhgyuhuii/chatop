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


def test_resolve_returns_symlink_path_not_dereferenced(tmp_path, monkeypatch):
    vol = tmp_path / "services"; fac = tmp_path / "factory"
    (fac / "dashboard-web").mkdir(parents=True)
    d = vol / "dashboard-web" / "1.6.0"; d.mkdir(parents=True)
    (d / "m.txt").write_text("v16")
    (vol / "dashboard-web" / "current").symlink_to("1.6.0")
    monkeypatch.setattr(services, "SERVICES_DIR", vol)
    monkeypatch.setattr(services, "FACTORY_DIR", fac)
    got = services.resolve("dashboard-web")
    # 返回的是 current 符号链接路径本身（活链），而非解引用后的物理 1.6.0 路径
    assert got.name == "current"
    assert (got / "m.txt").read_text() == "v16"
    # 换版：把 current 指向新目录，同一个 got 路径应立刻看到新内容（活链证明）
    d2 = vol / "dashboard-web" / "1.7.0"; d2.mkdir()
    (d2 / "m.txt").write_text("v17")
    import os as _os; _os.replace  # noqa
    (vol / "dashboard-web" / "current").unlink(); (vol / "dashboard-web" / "current").symlink_to("1.7.0")
    assert (got / "m.txt").read_text() == "v17"
