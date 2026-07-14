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


def test_apply_rejects_symlink_traversal(tmp_path):
    import os
    key = b"k" * 32
    sd = tmp_path / "services"
    # 造一个含逃逸软链成员的 tar
    tar = tmp_path / "station-9.9.9.tar.gz"
    with tarfile.open(tar, "w:gz") as tf:
        info = tarfile.TarInfo("evil")
        info.type = tarfile.SYMTYPE
        info.linkname = "../../escape"      # 逃逸到 dest 之外
        tf.addfile(info)
    sha = hashlib.sha256(tar.read_bytes()).hexdigest()
    sig = hmac.new(key, sha.encode(), hashlib.sha256).hexdigest()
    man = {"name": "station", "version": "9.9.9", "sha256": sha, "sig": sig,
           "min_base": "1.5.0", "needs_venv": False}
    with pytest.raises(updater.BundleError):
        updater.apply(tar, man, services_dir=sd, hmac_keys={"1": key},
                      health_check=lambda: True)


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


def test_apply_same_version_is_idempotent_noop(tmp_path, monkeypatch):
    key = b"k" * 32
    sd = tmp_path / "services"
    tar, man = _bundle(tmp_path, "station", "1.6.0", key, "sixzero")
    # 用计数替身包一层 _safe_extractall：证明第二次 apply 同一版本时完全不
    # 触碰解包/替换那套非原子操作，而是直接短路返回。
    calls = []
    orig_extract = updater._safe_extractall

    def _counting_extract(tf, dest):
        calls.append(dest)
        return orig_extract(tf, dest)

    monkeypatch.setattr(updater, "_safe_extractall", _counting_extract)

    res1 = updater.apply(tar, man, services_dir=sd, hmac_keys={"1": key},
                         health_check=lambda: True)
    assert res1.ok is True
    assert len(calls) == 1

    res2 = updater.apply(tar, man, services_dir=sd, hmac_keys={"1": key},
                         health_check=lambda: True)
    assert res2.ok is True
    assert res2.detail == "already current"
    assert len(calls) == 1  # 幂等短路：第二次不应该再走解包/替换

    cur = sd / "station" / "current"
    assert (cur / "v.txt").read_text() == "sixzero"
    name_dir = sd / "station"
    assert [p.name for p in name_dir.iterdir() if p.name.endswith(".tmp")] == []


def test_rollback_uses_history_not_lexical_order(tmp_path):
    # 词法排序下 "1.10.0" < "1.9.0"，若 rollback 按字典序挑选会选错；
    # 真实历史栈应该记住 apply 1.10.0 之前的版本是 1.9.0。
    key = b"k" * 32
    sd = tmp_path / "services"
    for ver, txt in [("1.9.0", "nine"), ("1.10.0", "ten")]:
        tar, man = _bundle(tmp_path, "station", ver, key, txt)
        updater.apply(tar, man, services_dir=sd, hmac_keys={"1": key},
                      health_check=lambda: True)
    res = updater.rollback("station", services_dir=sd)
    assert res.ok is True
    cur = sd / "station" / "current"
    assert (cur / "v.txt").read_text() == "nine"


def test_rollback_twice_does_not_pingpong(tmp_path):
    key = b"k" * 32
    sd = tmp_path / "services"
    for ver, txt in [("1.6.0", "a"), ("1.7.0", "b")]:
        tar, man = _bundle(tmp_path, "station", ver, key, txt)
        updater.apply(tar, man, services_dir=sd, hmac_keys={"1": key},
                      health_check=lambda: True)
    res1 = updater.rollback("station", services_dir=sd)
    assert res1.ok is True
    cur = sd / "station" / "current"
    assert (cur / "v.txt").read_text() == "a"
    # 历史栈已耗尽，不应该乒乓地跳回 1.7.0
    res2 = updater.rollback("station", services_dir=sd)
    assert res2.ok is False
    assert "no previous version" in res2.detail
    assert (cur / "v.txt").read_text() == "a"
