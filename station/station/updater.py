"""服务 bundle apply/rollback：验签→解包→原子软链切换→健康门→失败回滚。纯 stdlib。"""
from __future__ import annotations

import os
import tarfile
import time
import urllib.request
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


def _vkey(v: str):
    """数字版本键：把 "1.10.0" 排在 "1.9.0" 之后，而不是按字典序排到前面。"""
    import re
    return tuple(int(x) for x in re.findall(r"\d+", v)) or (0,)


def _versions(name_dir: Path) -> list[str]:
    if not name_dir.is_dir():
        return []
    return sorted((p.name for p in name_dir.iterdir()
                   if p.is_dir() and p.name != "current" and not p.name.endswith(".tmp")),
                  key=_vkey)


def _history_file(name_dir: Path) -> Path:
    return name_dir / ".history"


def _history_read(name_dir: Path) -> list[str] | None:
    """返回历史栈内容；`.history` 文件不存在时返回 None（区别于"存在但为空"）。"""
    hf = _history_file(name_dir)
    if not hf.exists():
        return None
    return [ln.strip() for ln in hf.read_text().splitlines() if ln.strip()]


def _history_write(name_dir: Path, stack: list[str]) -> None:
    _history_file(name_dir).write_text("\n".join(stack) + ("\n" if stack else ""))


def _history_push(name_dir: Path, version: str) -> None:
    stack = _history_read(name_dir) or []
    stack.append(version)
    _history_write(name_dir, stack)


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

    # 幂等短路：目标版本已经是 current 且物理目录还在，直接复检健康门返回，
    # 不要再走 rmtree→replace 那套非原子换版——那个窗口期 final 会短暂消失。
    final_existing = name_dir / version
    if prev == version and final_existing.is_dir():
        ok = health_check()
        return ApplyResult(ok, name, version, "already current" if ok else "health check failed")

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
        # 只在健康门通过的真实切换上，才把被替下的版本压入历史栈——
        # 失败自愈回滚那条路径不应该污染历史（否则会记出一条从未真正生效过的版本）。
        if prev is not None and prev != version:
            _history_push(name_dir, prev)
        return ApplyResult(True, name, version, "applied")
    # 健康门不过 → 回滚
    if prev is not None:
        _point_current(name_dir, prev)
    return ApplyResult(False, name, version, "health check failed; rolled back")


def rollback(name: str, *, services_dir: Path) -> ApplyResult:
    """把 current 指回真实的上一个版本：优先弹历史栈，栈不存在时退回启发式。"""
    name_dir = services_dir / name
    cur = _current_target(name_dir)
    history = _history_read(name_dir)
    if history is not None:
        # 历史栈存在（哪怕已耗尽为空）：只用它，不再退回启发式，避免耗尽后乒乓跳回。
        remaining = list(history)
        while remaining:
            candidate = remaining.pop()
            if candidate != cur and (name_dir / candidate).is_dir():
                _history_write(name_dir, remaining)
                _point_current(name_dir, candidate)
                return ApplyResult(True, name, candidate, "rolled back")
        _history_write(name_dir, remaining)
        return ApplyResult(False, name, cur or "", "no previous version")

    # 历史栈从未建立过（例如老数据/首次调用）：退回启发式——按数字版本号取最高的「另一个」版本。
    vers = _versions(name_dir)
    candidates = [v for v in vers if v != cur]
    if not candidates:
        return ApplyResult(False, name, cur or "", "no previous version")
    target = max(candidates, key=_vkey)
    _point_current(name_dir, target)
    return ApplyResult(True, name, target, "rolled back")


def _rmtree(p: Path) -> None:
    import shutil
    shutil.rmtree(p, ignore_errors=True)


def _safe_extractall(tf: tarfile.TarFile, dest: Path) -> None:
    """用 stdlib data 过滤器防目录穿越/软链逃逸/绝对路径；不依赖宿主发行版默认值。"""
    try:
        tf.extractall(dest, filter="data")
    except tarfile.FilterError as e:
        raise BundleError(f"unsafe bundle member: {e}")


def http_health_check(url: str = "http://127.0.0.1:8787/dashboard/api/system",
                      timeout: float = 30.0, interval: float = 1.0) -> Callable[[], bool]:
    """返回一个轮询就绪端点的健康检查闭包（供 apply 注入）。纯 stdlib urllib。

    注：仅探测 station 自身存活；按服务参数化就绪探测 + 重启后重载由 supervisor
    集成（后续阶段）负责。
    """
    def check() -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=3) as resp:
                    if resp.status == 200:
                        return True
            except Exception:
                pass
            time.sleep(interval)
        return False

    return check
