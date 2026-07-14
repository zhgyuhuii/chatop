"""服务 bundle apply/rollback：验签→解包→原子软链切换→健康门→失败回滚。纯 stdlib。"""
from __future__ import annotations

import json
import os
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from .bundle import BundleError, verify


@dataclass
class ApplyResult:
    ok: bool
    name: str
    version: str
    detail: str = ""


def _versions(name_dir: Path) -> list[str]:
    if not name_dir.is_dir():
        return []
    return sorted(p.name for p in name_dir.iterdir()
                  if p.is_dir() and p.name != "current" and not p.name.endswith(".tmp"))


def _point_current(name_dir: Path, version: str) -> None:
    """原子把 current 软链指向 version：建临时软链再 rename 覆盖。"""
    tmp = name_dir / f".current.{os.getpid()}.tmp"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(version)  # 相对软链
    os.replace(tmp, name_dir / "current")


def _current_target(name_dir: Path) -> str | None:
    cur = name_dir / "current"
    if cur.is_symlink():
        return os.readlink(cur)
    return None


def apply(tar_path: Path, manifest: Mapping, *, services_dir: Path,
          hmac_keys: Mapping[str, bytes], health_check: Callable[[], bool]) -> ApplyResult:
    """验签→解包到 <ver>.tmp 原子改名→切 current→健康门；失败回滚到 previous。"""
    name = str(manifest["name"])
    version = str(manifest["version"])
    verify(tar_path, manifest, hmac_keys)  # 不过直接抛 BundleError，current 未动

    name_dir = services_dir / name
    name_dir.mkdir(parents=True, exist_ok=True)
    prev = _current_target(name_dir)

    staging = name_dir / f"{version}.tmp"
    if staging.exists():
        _rmtree(staging)
    staging.mkdir()
    with tarfile.open(tar_path, "r:gz") as tf:
        _safe_extractall(tf, staging)
    final = name_dir / version
    if final.exists():
        _rmtree(final)
    os.replace(staging, final)

    _point_current(name_dir, version)
    if health_check():
        return ApplyResult(True, name, version, "applied")
    # 健康门不过 → 回滚
    if prev is not None:
        _point_current(name_dir, prev)
    return ApplyResult(False, name, version, "health check failed; rolled back")


def rollback(name: str, *, services_dir: Path) -> ApplyResult:
    """把 current 指回上一个版本（按版本名排序的倒数第二个）。"""
    name_dir = services_dir / name
    vers = _versions(name_dir)
    cur = _current_target(name_dir)
    candidates = [v for v in vers if v != cur]
    if not candidates:
        return ApplyResult(False, name, cur or "", "no previous version")
    target = candidates[-1]
    _point_current(name_dir, target)
    return ApplyResult(True, name, target, "rolled back")


def _rmtree(p: Path) -> None:
    import shutil
    shutil.rmtree(p, ignore_errors=True)


def _safe_extractall(tf: tarfile.TarFile, dest: Path) -> None:
    """防目录穿越：拒绝含 .. 或绝对路径的成员。"""
    base = dest.resolve()
    for m in tf.getmembers():
        target = (dest / m.name).resolve()
        if not str(target).startswith(str(base)):
            raise BundleError(f"unsafe path in bundle: {m.name}")
    tf.extractall(dest)
