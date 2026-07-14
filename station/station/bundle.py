"""服务 bundle 完整性 + 验签。纯 stdlib，密钥复用 chatop_license 的 HMAC 键。"""
from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from typing import Mapping


class BundleError(Exception):
    """bundle 校验失败（摘要不符 / 签名不符 / 无可用密钥）。"""


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(tar_path: Path, manifest: Mapping, hmac_keys: Mapping[str, bytes]) -> bool:
    """校验 bundle：payload sha256 与 manifest 一致，且 sig 是某把 HMAC 键对 sha256 的签名。

    抛 BundleError 表示不可信；返回 True 表示可信。hmac_keys: {kid: keybytes}。
    """
    actual = _digest(tar_path)
    want = str(manifest.get("sha256", ""))
    if not hmac.compare_digest(actual, want):
        raise BundleError(f"sha256 mismatch: {actual} != {want}")
    sig = str(manifest.get("sig", ""))
    if not sig or not hmac_keys:
        raise BundleError("missing signature or no hmac keys available")
    for key in hmac_keys.values():
        expect = hmac.new(key, want.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(expect, sig):
            return True
    raise BundleError("signature does not match any known key")
