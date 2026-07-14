"""python -m station rollback <service> CLI：给外层 supervisor 的自愈回滚入口。"""
import hashlib
import hmac
import tarfile
from pathlib import Path

import pytest
from station import updater
from station.__main__ import _rollback_cli


def _bundle(tmp_path: Path, name: str, ver: str, key: bytes, content: str):
    payload = tmp_path / f"pl-{ver}"
    payload.mkdir()
    (payload / "v.txt").write_text(content)
    tar = tmp_path / f"{name}-{ver}.tar.gz"
    with tarfile.open(tar, "w:gz") as tf:
        tf.add(payload / "v.txt", arcname="v.txt")
    sha = hashlib.sha256(tar.read_bytes()).hexdigest()
    sig = hmac.new(key, sha.encode(), hashlib.sha256).hexdigest()
    manifest = {"name": name, "version": ver, "sha256": sha, "sig": sig,
                "min_base": "1.5.0", "needs_venv": False}
    return tar, manifest


def test_rollback_cli_moves_current_back_to_previous(tmp_path, monkeypatch):
    key = b"k" * 32
    sd = tmp_path / "services"
    monkeypatch.setenv("CHATOP_SERVICES_DIR", str(sd))

    for ver, txt in [("1.6.0", "a"), ("1.7.0", "b")]:
        tar, man = _bundle(tmp_path, "station", ver, key, txt)
        updater.apply(tar, man, services_dir=sd, hmac_keys={"1": key},
                      health_check=lambda: True)

    cur = sd / "station" / "current"
    assert (cur / "v.txt").read_text() == "b"

    with pytest.raises(SystemExit) as exc:
        _rollback_cli("station")
    assert exc.value.code == 0
    assert (cur / "v.txt").read_text() == "a"


def test_rollback_cli_no_previous_exits_nonzero(tmp_path, monkeypatch):
    key = b"k" * 32
    sd = tmp_path / "services"
    monkeypatch.setenv("CHATOP_SERVICES_DIR", str(sd))
    tar, man = _bundle(tmp_path, "station", "1.6.0", key, "only")
    updater.apply(tar, man, services_dir=sd, hmac_keys={"1": key},
                  health_check=lambda: True)

    with pytest.raises(SystemExit) as exc:
        _rollback_cli("station")
    assert exc.value.code == 1


def test_rollback_cli_missing_service_arg_exits_2():
    with pytest.raises(SystemExit) as exc:
        _rollback_cli("")
    assert exc.value.code == 2
