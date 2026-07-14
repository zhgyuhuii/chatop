import hashlib
import hmac
import json
import tarfile
from pathlib import Path

import pytest
from station import bundle


def _make_bundle(tmp_path: Path, name: str, version: str, key: bytes, *, tamper=False):
    payload_dir = tmp_path / "payload"
    payload_dir.mkdir()
    (payload_dir / "hello.txt").write_text("hi")
    tar_path = tmp_path / f"{name}-{version}.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tf:
        tf.add(payload_dir / "hello.txt", arcname="hello.txt")

    # Compute sha and sig from clean payload
    sha = hashlib.sha256(tar_path.read_bytes()).hexdigest()
    sig = hmac.new(key, sha.encode(), hashlib.sha256).hexdigest()
    manifest = {"name": name, "version": version, "sha256": sha, "sig": sig,
                "min_base": "1.5.0", "needs_venv": False}
    (tmp_path / f"{name}-{version}.json").write_text(json.dumps(manifest))

    # Tamper AFTER manifest creation so file sha256 will not match
    if tamper:
        raw = tar_path.read_bytes()
        raw = raw + b"x"
        tar_path.write_bytes(raw)

    return tar_path, manifest


def test_verify_accepts_good_bundle(tmp_path):
    key = b"k" * 32
    tar_path, manifest = _make_bundle(tmp_path, "station", "1.6.0", key)
    assert bundle.verify(tar_path, manifest, {"1": key}) is True


def test_verify_rejects_bad_sha(tmp_path):
    key = b"k" * 32
    tar_path, manifest = _make_bundle(tmp_path, "station", "1.6.0", key)
    manifest["sha256"] = "0" * 64
    with pytest.raises(bundle.BundleError):
        bundle.verify(tar_path, manifest, {"1": key})


def test_verify_rejects_bad_sig(tmp_path):
    key = b"k" * 32
    tar_path, manifest = _make_bundle(tmp_path, "station", "1.6.0", key)
    manifest["sig"] = "deadbeef"
    with pytest.raises(bundle.BundleError):
        bundle.verify(tar_path, manifest, {"1": key})


def test_verify_rejects_tampered_payload(tmp_path):
    key = b"k" * 32
    tar_path, manifest = _make_bundle(tmp_path, "station", "1.6.0", key, tamper=True)
    with pytest.raises(bundle.BundleError):
        bundle.verify(tar_path, manifest, {"1": key})
