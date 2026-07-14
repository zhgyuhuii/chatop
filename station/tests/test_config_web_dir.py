import importlib
from pathlib import Path


def test_web_dir_uses_services_resolve(tmp_path, monkeypatch):
    monkeypatch.setenv("CHATOP_SERVICES_DIR", str(tmp_path / "services"))
    monkeypatch.setenv("CHATOP_FACTORY_DIR", str(tmp_path / "factory"))
    fac = tmp_path / "factory" / "dashboard-web" / "dist"
    fac.mkdir(parents=True)
    (fac / "index.html").write_text("<html></html>")
    from station import services, config
    importlib.reload(services)
    importlib.reload(config)
    # 缺 current → 回退 factory 的 dashboard-web/dist
    assert config.web_dir() == (tmp_path / "factory" / "dashboard-web" / "dist")
