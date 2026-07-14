import hashlib
import hmac
import json
import tarfile
from pathlib import Path

import pytest
from station import updater


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


def test_apply_swaps_current_on_health_ok(tmp_path):
    key = b"k" * 32
    sd = tmp_path / "services"
    tar, man = _bundle(tmp_path, "station", "1.6.0", key, "sixzero")
    res = updater.apply(tar, man, services_dir=sd, hmac_keys={"1": key},
                        health_check=lambda: True)
    assert res.ok is True
    cur = sd / "station" / "current"
    assert (cur / "v.txt").read_text() == "sixzero"


def test_apply_rolls_back_on_health_fail(tmp_path):
    key = b"k" * 32
    sd = tmp_path / "services"
    tar1, man1 = _bundle(tmp_path, "station", "1.6.0", key, "good")
    updater.apply(tar1, man1, services_dir=sd, hmac_keys={"1": key},
                  health_check=lambda: True)
    tar2, man2 = _bundle(tmp_path, "station", "1.7.0", key, "bad")
    res = updater.apply(tar2, man2, services_dir=sd, hmac_keys={"1": key},
                        health_check=lambda: False)
    assert res.ok is False
    cur = sd / "station" / "current"
    assert (cur / "v.txt").read_text() == "good"  # 回滚到上一版


def test_apply_rejects_bad_signature_before_touching_current(tmp_path):
    key = b"k" * 32
    sd = tmp_path / "services"
    tar, man = _bundle(tmp_path, "station", "1.6.0", key, "x")
    man["sig"] = "bad"
    with pytest.raises(updater.BundleError):
        updater.apply(tar, man, services_dir=sd, hmac_keys={"1": key},
                      health_check=lambda: True)
    assert not (sd / "station" / "current").exists()


def test_rollback_points_current_to_previous(tmp_path):
    key = b"k" * 32
    sd = tmp_path / "services"
    for ver, txt in [("1.6.0", "a"), ("1.7.0", "b")]:
        tar, man = _bundle(tmp_path, "station", ver, key, txt)
        updater.apply(tar, man, services_dir=sd, hmac_keys={"1": key},
                      health_check=lambda: True)
    updater.rollback("station", services_dir=sd)
    cur = sd / "station" / "current"
    assert (cur / "v.txt").read_text() == "a"
