# P1 · 工位服务解耦 + 卷内热更（A 地基）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 chatop 工位侧 station / agent-config / dashboard-web / openclaw-tool 从 `/opt` 只读镜像层解耦到 `chatop-home` 卷内的版本化服务区，实现验签→原子软链切换→健康门→自动回滚的免重打镜像热更新，并在大屏可视化更新/回滚。

**Architecture:** 镜像 `/opt/chatop/factory/<name>/` 存出厂 bundle 当兜底+首播种源；首启幂等播种到卷 `~/.chatop/services/<name>/<ver>/`，`current` 软链指生效版。station 经统一解析器 `services.resolve(name)` 从"卷内 current，缺失回退 factory"加载。updater 走验签(复用 chatop_license HMAC)/原子切换/健康门/回滚流水线，端点挂 station，大屏加面板。

**Tech Stack:** Python 3.11 纯 stdlib（station 复用 `/opt/station-venv` 的 fastapi/uvicorn；services/bundle/updater 模块纯 stdlib）、bash、React/TS（dashboard-web，Vite）、pytest、vitest。

**落点仓:** `/work/chatop`（main 分支）。**验证前缀:** `PYTHONPATH=/work/chatop/agent-config` 供 agentconfig import；station 测试用 `python3.11 -m pytest station/tests/`。

---

## 文件结构（先锁定边界）

**新建：**
- `station/station/services.py` — 服务区解析：`resolve(name)` 返回生效目录（卷 current 有效则用，否则 factory）。纯函数，无 IO 副作用外的状态。
- `station/station/bundle.py` — manifest 解析 + sha256 + HMAC 验签（复用 `chatop_license`）。
- `station/station/updater.py` — apply/rollback 流水线（解包/原子软链/健康门/回滚）。
- `station/station/updater_api.py` — station 端点（版本状态/apply/rollback）。
- `tools/build-bundle.sh` — 打服务 bundle + manifest（不走 Docker）。
- `app-manager/chatop-seed-services.sh` — 首启把 factory bundle 幂等播种到卷（WANT 哨兵）。
- `dashboard-web/src/updater/UpdaterPanel.tsx` + `updaterApi.ts` — 大屏更新面板。

**修改：**
- `station/station/config.py` — 加 `SERVICES_DIR`/`FACTORY_DIR`；`WEB_DIR` 改由 `services.resolve` 定。
- `station/station/api.py:119-121` — web 挂载用解析目录；注册 updater 路由。
- `station/start-station.sh` — `PYTHONPATH`/`OPENCLAW_TOOL_DIR` 指卷内 current，缺失回退 `/opt`。
- `Dockerfile` — 三服务 COPY 落点改 `/opt/chatop/factory/<name>/`；`custom_startup.sh` 加 seed-services 调用 + station supervisor。
- `dashboard-web/src/App.tsx` — 挂 `#/updater` 或在系统页加入面板入口。

**约定的服务名与路径（全计划一致引用）：**
- 服务名：`station`、`agent-config`、`dashboard-web`、`openclaw-tool`。
- 卷服务区：`$HOME/.chatop/services/<name>/<ver>/`，`current -> <ver>` 软链。
- 出厂区：`/opt/chatop/factory/<name>/`。
- manifest 字段：`name`、`version`、`sha256`、`sig`、`min_base`、`needs_venv`。

---

## Task 1: 服务区解析器 services.resolve

**Files:**
- Create: `station/station/services.py`
- Test: `station/tests/test_services.py`

- [ ] **Step 1: 写失败测试**

```python
# station/tests/test_services.py
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /work/chatop && python3.11 -m pytest station/tests/test_services.py -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'station.services'` 或 AttributeError）

- [ ] **Step 3: 写最小实现**

```python
# station/station/services.py
"""服务区解析：卷内 current 有效则用，否则回退镜像出厂副本。纯 stdlib。"""
from __future__ import annotations

import os
from pathlib import Path

HOME = Path(os.environ.get("HOME", "/home/admin"))
SERVICES_DIR = Path(os.environ.get("CHATOP_SERVICES_DIR", str(HOME / ".chatop/services")))
FACTORY_DIR = Path(os.environ.get("CHATOP_FACTORY_DIR", "/opt/chatop/factory"))


def resolve(name: str) -> Path:
    """返回服务 name 的生效目录。

    卷内 <SERVICES_DIR>/<name>/current 是有效目录（软链指向存在的版本）→ 用它；
    否则回退 <FACTORY_DIR>/<name>（镜像出厂副本，保证开机必起）。
    """
    cur = SERVICES_DIR / name / "current"
    try:
        if cur.is_dir():  # is_dir() 对悬空软链返回 False
            return cur.resolve()
    except OSError:
        pass
    return FACTORY_DIR / name
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /work/chatop && python3.11 -m pytest station/tests/test_services.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git -C /work/chatop add station/station/services.py station/tests/test_services.py
git -C /work/chatop commit -m "feat(station): add service-region resolver with factory fallback"
```

---

## Task 2: bundle manifest 解析 + HMAC 验签

**Files:**
- Create: `station/station/bundle.py`
- Test: `station/tests/test_bundle.py`
- 复用：`app-manager/chatop_license/gate.py` 的 `hmac_keys()`、`chatop_license/store.py` 的 HMAC 习惯

- [ ] **Step 1: 写失败测试**

```python
# station/tests/test_bundle.py
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
    raw = tar_path.read_bytes()
    if tamper:
        raw = raw + b"x"
        tar_path.write_bytes(raw)
    sha = hashlib.sha256(tar_path.read_bytes()).hexdigest()
    sig = hmac.new(key, sha.encode(), hashlib.sha256).hexdigest()
    manifest = {"name": name, "version": version, "sha256": sha, "sig": sig,
                "min_base": "1.5.0", "needs_venv": False}
    (tmp_path / f"{name}-{version}.json").write_text(json.dumps(manifest))
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /work/chatop && python3.11 -m pytest station/tests/test_bundle.py -v`
Expected: FAIL（`No module named 'station.bundle'`）

- [ ] **Step 3: 写最小实现**

```python
# station/station/bundle.py
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /work/chatop && python3.11 -m pytest station/tests/test_bundle.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git -C /work/chatop add station/station/bundle.py station/tests/test_bundle.py
git -C /work/chatop commit -m "feat(station): add bundle integrity + HMAC signature verify"
```

---

## Task 3: updater apply/rollback 流水线（不含健康门 IO，先纯逻辑）

**Files:**
- Create: `station/station/updater.py`
- Test: `station/tests/test_updater.py`

设计：`apply(tar_path, manifest, *, services_dir, hmac_keys, health_check)` 与 `rollback(name, *, services_dir)`。`health_check` 是注入的可调用（`() -> bool`），便于单测不起真进程。

- [ ] **Step 1: 写失败测试**

```python
# station/tests/test_updater.py
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /work/chatop && python3.11 -m pytest station/tests/test_updater.py -v`
Expected: FAIL（`No module named 'station.updater'`）

- [ ] **Step 3: 写最小实现**

```python
# station/station/updater.py
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /work/chatop && python3.11 -m pytest station/tests/test_updater.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git -C /work/chatop add station/station/updater.py station/tests/test_updater.py
git -C /work/chatop commit -m "feat(station): add updater apply/rollback with atomic symlink swap + health gate"
```

---

## Task 4: config.py 接服务区，web_dir 走解析

**Files:**
- Modify: `station/station/config.py`
- Test: `station/tests/test_config_web_dir.py`

- [ ] **Step 1: 写失败测试**

```python
# station/tests/test_config_web_dir.py
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /work/chatop && python3.11 -m pytest station/tests/test_config_web_dir.py -v`
Expected: FAIL（`AttributeError: module 'station.config' has no attribute 'web_dir'`）

- [ ] **Step 3: 改实现**

在 `station/station/config.py` 末尾追加（保留原有常量；`WEB_DIR` 常量不再直接用，改用函数）：

```python
from . import services  # noqa: E402  放文件末尾避免循环 import


def web_dir():
    """dashboard-web 生效 dist 目录：卷内 current/dist，缺失回退 factory/dashboard-web/dist。"""
    return services.resolve("dashboard-web") / "dist"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /work/chatop && python3.11 -m pytest station/tests/test_config_web_dir.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git -C /work/chatop add station/station/config.py station/tests/test_config_web_dir.py
git -C /work/chatop commit -m "feat(station): resolve dashboard web dir from service region"
```

---

## Task 5: api.py 用解析目录挂 web + 注册 updater 路由

**Files:**
- Modify: `station/station/api.py`（当前 119-121 行 `wd = web_dir or config.WEB_DIR`）
- Create: `station/station/updater_api.py`
- Test: `station/tests/test_updater_api.py`

- [ ] **Step 1: 写失败测试**

```python
# station/tests/test_updater_api.py
from fastapi.testclient import TestClient
from station.api import create_app
from station.events import EventHub
from station.tasks.store import TaskStore
from station.tasks.dispatcher import Dispatcher


def _client(tmp_path):
    store = TaskStore(tmp_path / "s.db")
    hub = EventHub()
    disp = Dispatcher(store, hub, nickname="t")
    app = create_app(store, hub, disp)
    return TestClient(app)


def test_versions_endpoint_lists_services(tmp_path, monkeypatch):
    monkeypatch.setenv("CHATOP_SERVICES_DIR", str(tmp_path / "services"))
    monkeypatch.setenv("CHATOP_FACTORY_DIR", str(tmp_path / "factory"))
    c = _client(tmp_path)
    r = c.get("/dashboard/api/updater/versions")
    assert r.status_code == 200
    body = r.json()
    assert "services" in body
    names = {s["name"] for s in body["services"]}
    assert {"station", "agent-config", "dashboard-web", "openclaw-tool"} <= names
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /work/chatop && python3.11 -m pytest station/tests/test_updater_api.py -v`
Expected: FAIL（404，路由未注册）

- [ ] **Step 3: 写实现**

新建 `station/station/updater_api.py`：

```python
# station/station/updater_api.py
"""updater 只读+操作端点，挂在 /dashboard/api/updater/*。"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter

from . import services

_SERVICE_NAMES = ["station", "agent-config", "dashboard-web", "openclaw-tool"]


def _active_version(name: str) -> str:
    cur = services.SERVICES_DIR / name / "current"
    if cur.is_symlink():
        return os.readlink(cur)
    return "factory"


def create_router() -> APIRouter:
    r = APIRouter(prefix="/dashboard/api/updater")

    @r.get("/versions")
    def versions():
        return {"services": [
            {"name": n, "active": _active_version(n),
             "path": str(services.resolve(n))}
            for n in _SERVICE_NAMES
        ]}

    return r
```

在 `station/station/api.py` 里：把第 119-121 行的 `wd = web_dir or config.WEB_DIR` 改为用函数解析，并注册路由。找到：

```python
    wd = web_dir or config.WEB_DIR
    if ...
        app.mount("/dashboard", StaticFiles(directory=str(wd), html=True), name="web")
```

改为：

```python
    wd = web_dir or config.web_dir()
    from .updater_api import create_router as _updater_router
    app.include_router(_updater_router())
    if wd.exists():
        app.mount("/dashboard", StaticFiles(directory=str(wd), html=True), name="web")
```

（注意：`include_router` 必须在 `app.mount("/dashboard", ...)` 之前，否则 StaticFiles 的 catch-all 会吞掉 `/dashboard/api/updater/*`。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /work/chatop && python3.11 -m pytest station/tests/test_updater_api.py station/tests/test_agentcfg_api.py -v`
Expected: PASS（新测试通过，且原 agentcfg 端点未回归）

- [ ] **Step 5: 提交**

```bash
git -C /work/chatop add station/station/updater_api.py station/station/api.py station/tests/test_updater_api.py
git -C /work/chatop commit -m "feat(station): mount web from resolved dir + updater versions endpoint"
```

---

## Task 6: updater apply/rollback 端点 + 健康门（轮询 /dashboard/api/system）

**Files:**
- Modify: `station/station/updater_api.py`
- Modify: `station/station/updater.py`（加 `http_health_check` 工厂）
- Test: `station/tests/test_updater_api.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 station/tests/test_updater_api.py
import hashlib, hmac, json, tarfile
from pathlib import Path


def _make_inbox_bundle(inbox: Path, name: str, ver: str, key: bytes):
    inbox.mkdir(parents=True, exist_ok=True)
    payload = inbox / f"pl{ver}"; payload.mkdir()
    (payload / "v.txt").write_text(ver)
    tar = inbox / f"{name}-{ver}.tar.gz"
    with tarfile.open(tar, "w:gz") as tf:
        tf.add(payload / "v.txt", arcname="v.txt")
    sha = hashlib.sha256(tar.read_bytes()).hexdigest()
    sig = hmac.new(key, sha.encode(), hashlib.sha256).hexdigest()
    (inbox / f"{name}-{ver}.json").write_text(json.dumps(
        {"name": name, "version": ver, "sha256": sha, "sig": sig,
         "min_base": "1.5.0", "needs_venv": False}))
    return tar


def test_apply_endpoint_applies_bundle(tmp_path, monkeypatch):
    key = b"k" * 32
    monkeypatch.setenv("CHATOP_SERVICES_DIR", str(tmp_path / "services"))
    monkeypatch.setenv("CHATOP_FACTORY_DIR", str(tmp_path / "factory"))
    monkeypatch.setenv("CHATOP_UPDATER_INBOX", str(tmp_path / "inbox"))
    monkeypatch.setenv("CHATOP_LICENSE_KEYS_FILE", str(tmp_path / "keys.json"))
    (tmp_path / "keys.json").write_text(json.dumps(
        {"active_key_id": 1, "hmac_keys": {"1": key.hex()}}))
    _make_inbox_bundle(tmp_path / "inbox", "agent-config", "1.6.0", key)
    c = _client(tmp_path)
    r = c.post("/dashboard/api/updater/apply",
               json={"name": "agent-config", "version": "1.6.0", "health": "skip"})
    assert r.status_code == 200 and r.json()["ok"] is True
    cur = tmp_path / "services" / "agent-config" / "current"
    assert (cur / "v.txt").read_text() == "1.6.0"
```

注意：license-keys.json 里 `hmac_keys` 存的是 **hex 字符串**（见 `gate.py` 读取处 `bytes.fromhex`），测试据此写。端点从 `chatop_license.gate.hmac_keys()` 取键。`health="skip"` 让本地测试跳过起真服务。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /work/chatop && python3.11 -m pytest station/tests/test_updater_api.py::test_apply_endpoint_applies_bundle -v`
Expected: FAIL（404 或缺 apply 路由）

- [ ] **Step 3: 写实现**

在 `station/station/updater.py` 追加健康门工厂：

```python
def http_health_check(url: str = "http://127.0.0.1:8787/dashboard/api/system",
                      timeout: float = 30.0, interval: float = 1.0) -> Callable[[], bool]:
    """返回一个轮询就绪端点的健康检查闭包（供 apply 注入）。纯 stdlib urllib。"""
    import time
    import urllib.request

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
```

在 `station/station/updater_api.py` 追加 apply/rollback 端点：

```python
import json
from pathlib import Path

from fastapi import Body, HTTPException

from . import updater
from .bundle import BundleError

try:
    from chatop_license.gate import hmac_keys as _license_hmac_keys
except Exception:  # 引擎/许可库缺失时降级
    def _license_hmac_keys():
        return {}

_INBOX = Path(os.environ.get("CHATOP_UPDATER_INBOX", str(services.HOME / ".chatop/inbox")))
```

在 `create_router()` 内 `@r.get("/versions")` 之后追加：

```python
    @r.post("/apply")
    def apply_bundle(body: dict = Body(...)):
        name = str(body.get("name", ""))
        version = str(body.get("version", ""))
        man_path = _INBOX / f"{name}-{version}.json"
        tar_path = _INBOX / f"{name}-{version}.tar.gz"
        if not man_path.exists() or not tar_path.exists():
            raise HTTPException(404, f"bundle {name}-{version} not found in inbox")
        manifest = json.loads(man_path.read_text())
        keys = {k: bytes.fromhex(v) if isinstance(v, str) else v
                for k, v in _license_hmac_keys().items()}
        health = updater.http_health_check() if body.get("health") != "skip" else (lambda: True)
        try:
            res = updater.apply(tar_path, manifest, services_dir=services.SERVICES_DIR,
                                hmac_keys=keys, health_check=health)
        except BundleError as e:
            raise HTTPException(400, f"bundle verify failed: {e}")
        return {"ok": res.ok, "name": res.name, "version": res.version, "detail": res.detail}

    @r.post("/rollback")
    def rollback_bundle(body: dict = Body(...)):
        name = str(body.get("name", ""))
        res = updater.rollback(name, services_dir=services.SERVICES_DIR)
        return {"ok": res.ok, "name": res.name, "version": res.version, "detail": res.detail}
```

注意 `_license_hmac_keys()` 已返回 `{kid: keybytes}`（`gate.py` 内部做过 `bytes.fromhex`）；上面 `bytes.fromhex(v) if isinstance(v, str)` 是双保险。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /work/chatop && python3.11 -m pytest station/tests/test_updater_api.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git -C /work/chatop add station/station/updater.py station/station/updater_api.py station/tests/test_updater_api.py
git -C /work/chatop commit -m "feat(station): updater apply/rollback endpoints with HTTP health gate"
```

---

## Task 7: build-bundle.sh 打包脚本

**Files:**
- Create: `tools/build-bundle.sh`
- Test: `station/tests/test_build_bundle.sh`（bash 断言脚本）

- [ ] **Step 1: 写失败测试**

```bash
# station/tests/test_build_bundle.sh
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KEY="$(printf 'k%.0s' {1..64})"   # 64 hex 字符
OUT="$(mktemp -d)"
"$ROOT/tools/build-bundle.sh" agent-config 1.6.0 "$KEY" "$OUT"
test -f "$OUT/agent-config-1.6.0.tar.gz" || { echo "FAIL: no tarball"; exit 1; }
test -f "$OUT/agent-config-1.6.0.json" || { echo "FAIL: no manifest"; exit 1; }
python3.11 - "$OUT/agent-config-1.6.0.json" "$OUT/agent-config-1.6.0.tar.gz" "$KEY" <<'PY'
import hashlib, hmac, json, sys
man = json.load(open(sys.argv[1])); tar = sys.argv[2]; key = bytes.fromhex(sys.argv[3])
sha = hashlib.sha256(open(tar,'rb').read()).hexdigest()
assert man["sha256"] == sha, "sha mismatch"
assert man["sig"] == hmac.new(key, sha.encode(), hashlib.sha256).hexdigest(), "sig mismatch"
assert man["name"] == "agent-config" and man["version"] == "1.6.0"
print("OK")
PY
echo "PASS"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /work/chatop && bash station/tests/test_build_bundle.sh`
Expected: FAIL（`build-bundle.sh: No such file`）

- [ ] **Step 3: 写实现**

```bash
# tools/build-bundle.sh
#!/usr/bin/env bash
# 用法: build-bundle.sh <name> <version> <hmac_key_hex> <out_dir>
# 从仓库源打一个服务 bundle(.tar.gz) + manifest(.json)，不走 Docker。
set -euo pipefail
NAME="$1"; VER="$2"; KEY_HEX="$3"; OUT="$4"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$OUT"

# 各服务的源目录 → bundle 内布局
case "$NAME" in
  station)       SRC="$ROOT/station/station"; ARC="station" ;;
  agent-config)  SRC="$ROOT/agent-config/agentconfig"; ARC="agentconfig" ;;
  openclaw-tool) SRC="$ROOT/openclaw-tool"; ARC="." ;;
  dashboard-web) SRC="$ROOT/dashboard-web/dist"; ARC="dist" ;;
  *) echo "unknown service: $NAME" >&2; exit 2 ;;
esac
[ -d "$SRC" ] || { echo "source not found: $SRC" >&2; exit 2; }

TAR="$OUT/${NAME}-${VER}.tar.gz"
if [ "$ARC" = "." ]; then
  tar -C "$SRC" -czf "$TAR" .
else
  tar -C "$(dirname "$SRC")" -czf "$TAR" "$(basename "$SRC")"
fi

SHA="$(sha256sum "$TAR" | cut -d' ' -f1)"
SIG="$(python3.11 -c "import hmac,hashlib,sys;print(hmac.new(bytes.fromhex(sys.argv[1]),sys.argv[2].encode(),hashlib.sha256).hexdigest())" "$KEY_HEX" "$SHA")"
cat > "$OUT/${NAME}-${VER}.json" <<EOF
{"name":"$NAME","version":"$VER","sha256":"$SHA","sig":"$SIG","min_base":"1.5.0","needs_venv":false}
EOF
echo "built $TAR"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /work/chatop && chmod +x tools/build-bundle.sh && bash station/tests/test_build_bundle.sh`
Expected: 末行 `PASS`

- [ ] **Step 5: 提交**

```bash
git -C /work/chatop add tools/build-bundle.sh station/tests/test_build_bundle.sh
git -C /work/chatop commit -m "feat(tools): build-bundle.sh packages service bundles with signed manifest"
```

---

## Task 8: chatop-seed-services.sh 首启播种（WANT 哨兵 + 幂等）

**Files:**
- Create: `app-manager/chatop-seed-services.sh`
- Test: `station/tests/test_seed_services.sh`
- 参考现有：`app-manager/chatop-seed-home.sh` 的 `WANT` 哨兵 + `cp -an` 幂等模式

- [ ] **Step 1: 写失败测试**

```bash
# station/tests/test_seed_services.sh
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FAC="$(mktemp -d)"; VOL="$(mktemp -d)"
# 造出厂副本
for n in station agent-config dashboard-web openclaw-tool; do
  mkdir -p "$FAC/$n"; echo "factory-1.5.9" > "$FAC/$n/marker.txt"
done
export CHATOP_FACTORY_DIR="$FAC" CHATOP_SERVICES_DIR="$VOL" CHATOP_SERVICES_WANT=1
bash "$ROOT/app-manager/chatop-seed-services.sh"
# 首播种后：每个服务 current 指向 v1.5.9，marker 存在
for n in station agent-config dashboard-web openclaw-tool; do
  test -L "$VOL/$n/current" || { echo "FAIL: no current for $n"; exit 1; }
  test -f "$VOL/$n/current/marker.txt" || { echo "FAIL: no marker for $n"; exit 1; }
done
# 幂等：用户已升级 station 到更高版，再跑一次不得覆盖
mkdir -p "$VOL/station/9.9.9"; echo "user-999" > "$VOL/station/9.9.9/marker.txt"
ln -sfn 9.9.9 "$VOL/station/current"
bash "$ROOT/app-manager/chatop-seed-services.sh"
test "$(cat "$VOL/station/current/marker.txt")" = "user-999" || { echo "FAIL: clobbered user version"; exit 1; }
echo "PASS"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /work/chatop && bash station/tests/test_seed_services.sh`
Expected: FAIL（脚本不存在）

- [ ] **Step 3: 写实现**

```bash
# app-manager/chatop-seed-services.sh
# 首启把镜像出厂服务 bundle 幂等播种到 chatop-home 卷的服务区。
# 卷里没有该服务 → 播种为版本 vFACTORY 并建 current 软链；已有 current → 不动(尊重用户升级)。
set -euo pipefail
FAC="${CHATOP_FACTORY_DIR:-/opt/chatop/factory}"
VOL="${CHATOP_SERVICES_DIR:-$HOME/.chatop/services}"
FVER="${CHATOP_FACTORY_VERSION:-$(cat /opt/chatop/factory/VERSION 2>/dev/null || echo 0.0.0)}"

for n in station agent-config dashboard-web openclaw-tool; do
  [ -d "$FAC/$n" ] || continue
  dst="$VOL/$n"
  if [ -L "$dst/current" ] && [ -e "$dst/current" ]; then
    continue   # 已有生效版(可能是用户升级过的)，不覆盖
  fi
  mkdir -p "$dst/$FVER"
  cp -an "$FAC/$n/." "$dst/$FVER/" 2>/dev/null || cp -rn "$FAC/$n/." "$dst/$FVER/"
  ln -sfn "$FVER" "$dst/current"
done
echo "seeded services into $VOL (factory v$FVER)"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /work/chatop && bash station/tests/test_seed_services.sh`
Expected: 末行 `PASS`

- [ ] **Step 5: 提交**

```bash
git -C /work/chatop add app-manager/chatop-seed-services.sh station/tests/test_seed_services.sh
git -C /work/chatop commit -m "feat(app-manager): seed factory service bundles into volume idempotently"
```

---

## Task 9: start-station.sh 加载路径改造（指卷内 current，回退 /opt）

**Files:**
- Modify: `station/start-station.sh`
- Test: `station/tests/test_start_station_paths.sh`

- [ ] **Step 1: 写失败测试**

```bash
# station/tests/test_start_station_paths.sh
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VOL="$(mktemp -d)"; FAC="$(mktemp -d)"
mkdir -p "$VOL/agent-config/1.6.0/agentconfig" "$VOL/agent-config"
ln -sfn 1.6.0 "$VOL/agent-config/current"
mkdir -p "$VOL/openclaw-tool/1.6.0"; ln -sfn 1.6.0 "$VOL/openclaw-tool/current"
export CHATOP_SERVICES_DIR="$VOL" CHATOP_FACTORY_DIR="$FAC" STATION_DRY_RUN=1
out="$(bash "$ROOT/station/start-station.sh")"
echo "$out" | grep -q "PYTHONPATH=$VOL/agent-config/current" || { echo "FAIL: PYTHONPATH not volume"; exit 1; }
echo "$out" | grep -q "OPENCLAW_TOOL_DIR=$VOL/openclaw-tool/current" || { echo "FAIL: OPENCLAW_TOOL_DIR not volume"; exit 1; }
echo "PASS"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /work/chatop && bash station/tests/test_start_station_paths.sh`
Expected: FAIL（当前脚本硬编码 `/opt/agent-config`，且无 `STATION_DRY_RUN`）

- [ ] **Step 3: 改实现**

把 `station/start-station.sh` 改为（新增服务区解析 + dry-run 便于测试）：

```bash
#!/usr/bin/env bash
set -e
export STATION_PORT="${STATION_PORT:-8787}"
export APPS_CATALOG="${APPS_CATALOG:-/etc/chatop/apps-catalog.json}"

SVC="${CHATOP_SERVICES_DIR:-$HOME/.chatop/services}"
FAC="${CHATOP_FACTORY_DIR:-/opt/chatop/factory}"

# 服务生效目录：卷内 current 有效则用，否则回退出厂 factory（缺失再退旧 /opt 兼容）
resolve() { # $1=service name  $2=fallback-opt-path
  if [ -d "$SVC/$1/current" ]; then echo "$SVC/$1/current";
  elif [ -d "$FAC/$1" ]; then echo "$FAC/$1";
  else echo "$2"; fi
}

AGENT_CFG_DIR="$(resolve agent-config /opt/agent-config)"
OPENCLAW_DIR="$(resolve openclaw-tool /opt/openclaw-tool)"
STATION_DIR="$(resolve station /opt/station/station)"

# agent-config bundle 内层是 agentconfig/；PYTHONPATH 要指其父，import 名 agentconfig
if [ -d "$AGENT_CFG_DIR/agentconfig" ]; then PYPARENT="$AGENT_CFG_DIR"; else PYPARENT="/opt/agent-config"; fi
export PYTHONPATH="${PYPARENT}${PYTHONPATH:+:$PYTHONPATH}"
export OPENCLAW_TOOL_DIR="$OPENCLAW_DIR"

if [ "${STATION_DRY_RUN:-0}" = "1" ]; then
  echo "PYTHONPATH=$PYTHONPATH"
  echo "OPENCLAW_TOOL_DIR=$OPENCLAW_TOOL_DIR"
  echo "STATION_DIR=$STATION_DIR"
  exit 0
fi

# station 源可能在卷内 current/station（bundle 内层 station/），也可能出厂 /opt/station/station
if [ -d "$STATION_DIR/station" ]; then cd "$STATION_DIR"; else cd /opt/station; fi
exec /opt/station-venv/bin/python -m station
```

注意 dry-run 打印的 `PYTHONPATH` 需等于测试期望的 `$VOL/agent-config/current`（因为 bundle 内层是 `agentconfig/`，父就是 `current`）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /work/chatop && bash station/tests/test_start_station_paths.sh`
Expected: 末行 `PASS`

- [ ] **Step 5: 提交**

```bash
git -C /work/chatop add station/start-station.sh station/tests/test_start_station_paths.sh
git -C /work/chatop commit -m "feat(station): load agent-config/openclaw/station from volume current with /opt fallback"
```

---

## Task 10: Dockerfile 出厂布局 + 首启 seed 接线 + station supervisor

**Files:**
- Modify: `Dockerfile`（COPY 落点 + custom_startup）
- 验证：`python3.11 -m py_compile` 无关；此任务靠人工核对 diff + 后续集成冒烟

- [ ] **Step 1: 改 COPY 落点到 /opt/chatop/factory**

在 `Dockerfile` 产品层，把现有三处：
```
COPY station/station/ /opt/station/station/
COPY --from=dashweb /src/dist/ /opt/station/station/web/
COPY agent-config/agentconfig/ /opt/agent-config/agentconfig/
```
补充出厂副本（保留原 /opt 路径做旧兼容，同时建 factory 布局）：
```
# === 出厂服务 bundle（首启播种源 + 兜底）===
COPY station/station/        /opt/chatop/factory/station/station/
COPY --from=dashweb /src/dist/ /opt/chatop/factory/dashboard-web/dist/
COPY agent-config/agentconfig/ /opt/chatop/factory/agent-config/agentconfig/
COPY openclaw-tool/           /opt/chatop/factory/openclaw-tool/
COPY VERSION                  /opt/chatop/factory/VERSION
COPY app-manager/chatop-seed-services.sh /usr/local/bin/chatop-seed-services.sh
RUN sed -i 's/\r$//' /usr/local/bin/chatop-seed-services.sh && chmod +x /usr/local/bin/chatop-seed-services.sh
```

- [ ] **Step 2: custom_startup 加 seed + supervisor**

在 `Dockerfile` 生成 `custom_startup.sh` 的那段 `printf` 里，`start-station.sh` 那行改为先 seed、再用极简 supervisor 常驻拉起（收 SIGTERM 自动重拉，供 updater 热重启）：
```
/usr/local/bin/chatop-seed-services.sh >/tmp/seed-services.log 2>&1
( while true; do /usr/local/bin/start-station.sh >/tmp/station.log 2>&1; sleep 1; done ) &
```
（替换原 `/usr/local/bin/start-station.sh >/tmp/station.log 2>&1 &` 一行。）

- [ ] **Step 3: 语法自检**

Run: `cd /work/chatop && grep -n "chatop/factory\|chatop-seed-services\|while true; do /usr/local/bin/start-station" Dockerfile`
Expected: 能看到新增的 factory COPY、seed 脚本、supervisor 循环三处。

- [ ] **Step 4: 提交**

```bash
git -C /work/chatop add Dockerfile
git -C /work/chatop commit -m "feat(image): ship factory service bundles + seed on boot + station supervisor for hot-restart"
```

> 注：本任务不触发镜像构建（本机 7.3G 内存会 OOM，见镜像构建另案）。构建验证在集成阶段用大内存机或经典 builder 单独跑。

---

## Task 11: dashboard-web updater 面板

**Files:**
- Create: `dashboard-web/src/updater/updaterApi.ts`
- Create: `dashboard-web/src/updater/UpdaterPanel.tsx`
- Modify: `dashboard-web/src/App.tsx`（加 `#/updater` 路由入口）
- Test: `dashboard-web/src/updater/updaterApi.test.ts`（vitest）

- [ ] **Step 1: 写失败测试**

```typescript
// dashboard-web/src/updater/updaterApi.test.ts
import { describe, it, expect, vi } from "vitest";
import { fetchVersions, applyBundle } from "./updaterApi";

describe("updaterApi", () => {
  it("fetchVersions hits the versions endpoint", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ services: [{ name: "station", active: "1.6.0", path: "/x" }] }),
        { status: 200 }));
    const r = await fetchVersions();
    expect(spy).toHaveBeenCalledWith("/dashboard/api/updater/versions");
    expect(r.services[0].name).toBe("station");
  });

  it("applyBundle posts name+version", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true, name: "station", version: "1.7.0", detail: "applied" }),
        { status: 200 }));
    const r = await applyBundle("station", "1.7.0");
    expect(spy).toHaveBeenCalledWith("/dashboard/api/updater/apply", expect.objectContaining({ method: "POST" }));
    expect(r.ok).toBe(true);
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /work/chatop/dashboard-web && npx vitest run src/updater/updaterApi.test.ts`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 写实现**

```typescript
// dashboard-web/src/updater/updaterApi.ts
export interface ServiceVersion { name: string; active: string; path: string; }
export interface VersionsResp { services: ServiceVersion[]; }
export interface ApplyResp { ok: boolean; name: string; version: string; detail: string; }

export async function fetchVersions(): Promise<VersionsResp> {
  const r = await fetch("/dashboard/api/updater/versions");
  if (!r.ok) throw new Error(`versions ${r.status}`);
  return r.json();
}

export async function applyBundle(name: string, version: string): Promise<ApplyResp> {
  const r = await fetch("/dashboard/api/updater/apply", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ name, version }),
  });
  return r.json();
}

export async function rollback(name: string): Promise<ApplyResp> {
  const r = await fetch("/dashboard/api/updater/rollback", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ name }),
  });
  return r.json();
}
```

```tsx
// dashboard-web/src/updater/UpdaterPanel.tsx
import { useEffect, useState } from "react";
import { fetchVersions, applyBundle, rollback, ServiceVersion } from "./updaterApi";

export function UpdaterPanel() {
  const [svcs, setSvcs] = useState<ServiceVersion[]>([]);
  const [busy, setBusy] = useState("");
  const reload = () => fetchVersions().then((r) => setSvcs(r.services)).catch(() => {});
  useEffect(() => { reload(); }, []);
  return (
    <div className="updater-panel">
      <h2>服务版本 · 热更</h2>
      <table>
        <thead><tr><th>服务</th><th>生效版本</th><th>操作</th></tr></thead>
        <tbody>
          {svcs.map((s) => (
            <tr key={s.name}>
              <td>{s.name}</td><td>{s.active}</td>
              <td>
                <button disabled={busy === s.name}
                  onClick={async () => { setBusy(s.name); await rollback(s.name); await reload(); setBusy(""); }}>
                  回滚上一版
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

在 `dashboard-web/src/App.tsx` 的 hash 路由处（已有 `#/config` 分支），加入 `#/updater` → `<UpdaterPanel/>`：找到渲染 `ConfigCenter` 的条件分支，仿照它加：
```tsx
if (route === "#/updater") return <UpdaterPanel />;
```
并在文件顶部 `import { UpdaterPanel } from "./updater/UpdaterPanel";`。

- [ ] **Step 4: 跑测试确认通过 + typecheck**

Run: `cd /work/chatop/dashboard-web && npx vitest run src/updater/updaterApi.test.ts && npx tsc --noEmit`
Expected: 测试 PASS，tsc 无新错误

- [ ] **Step 5: 提交**

```bash
git -C /work/chatop add dashboard-web/src/updater/ dashboard-web/src/App.tsx
git -C /work/chatop commit -m "feat(dashboard): updater panel — view versions and one-click rollback"
```

---

## Task 12: app-manager 市场来源（拉版本化 bundle 到 inbox）

**Files:**
- Create: `app-manager/chatop-fetch-bundle.sh`
- Test: `station/tests/test_fetch_bundle.sh`
- 参考：`app-manager/chatop-fetch.sh` + `mirrors.conf`

- [ ] **Step 1: 写失败测试（本地 file:// 源，不联网）**

```bash
# station/tests/test_fetch_bundle.sh
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$(mktemp -d)"; INBOX="$(mktemp -d)"
echo "payload" > "$SRC/station-1.7.0.tar.gz"
echo '{"name":"station","version":"1.7.0"}' > "$SRC/station-1.7.0.json"
export CHATOP_UPDATER_INBOX="$INBOX" CHATOP_BUNDLE_BASE="file://$SRC"
bash "$ROOT/app-manager/chatop-fetch-bundle.sh" station 1.7.0
test -f "$INBOX/station-1.7.0.tar.gz" && test -f "$INBOX/station-1.7.0.json" || { echo FAIL; exit 1; }
echo "PASS"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd /work/chatop && bash station/tests/test_fetch_bundle.sh`
Expected: FAIL（脚本不存在）

- [ ] **Step 3: 写实现**

```bash
# app-manager/chatop-fetch-bundle.sh
# 用法: chatop-fetch-bundle.sh <name> <version>
# 从 CHATOP_BUNDLE_BASE 下载 <name>-<version>.{tar.gz,json} 到 updater inbox。
# 支持 file:// 与 http(s)://；http 走 curl（复用 mirrors 习惯）。
set -euo pipefail
NAME="$1"; VER="$2"
INBOX="${CHATOP_UPDATER_INBOX:-$HOME/.chatop/inbox}"
BASE="${CHATOP_BUNDLE_BASE:?set CHATOP_BUNDLE_BASE (e.g. https://mirror/chatop/bundles)}"
mkdir -p "$INBOX"
fetch() { # $1=filename
  local url="$BASE/$1" dst="$INBOX/$1"
  case "$url" in
    file://*) cp "${url#file://}" "$dst" ;;
    *) curl -fsSL --retry 3 -o "$dst" "$url" ;;
  esac
}
fetch "${NAME}-${VER}.tar.gz"
fetch "${NAME}-${VER}.json"
echo "fetched ${NAME}-${VER} into $INBOX"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd /work/chatop && chmod +x app-manager/chatop-fetch-bundle.sh && bash station/tests/test_fetch_bundle.sh`
Expected: 末行 `PASS`

- [ ] **Step 5: 提交**

```bash
git -C /work/chatop add app-manager/chatop-fetch-bundle.sh station/tests/test_fetch_bundle.sh
git -C /work/chatop commit -m "feat(app-manager): fetch versioned service bundles into updater inbox"
```

---

## Task 13: 端到端冒烟（打包→投递→apply→回滚，全走真文件）

**Files:**
- Create: `station/tests/test_e2e_hotupdate.sh`

- [ ] **Step 1: 写冒烟脚本**

```bash
# station/tests/test_e2e_hotupdate.sh
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KEY="$(printf 'a%.0s' {1..64})"
VOL="$(mktemp -d)"; INBOX="$(mktemp -d)"; OUT="$(mktemp -d)"
# 1) 打 agent-config bundle 到 inbox
"$ROOT/tools/build-bundle.sh" agent-config 1.6.0 "$KEY" "$INBOX"
# 2) 用 updater 纯逻辑 apply（health skip），断言 current 生效
python3.11 - "$ROOT" "$VOL" "$INBOX" "$KEY" <<'PY'
import sys, json, os
sys.path.insert(0, sys.argv[1] + "/station")
from station import updater
root, vol, inbox, key = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
from pathlib import Path
man = json.load(open(f"{inbox}/agent-config-1.6.0.json"))
res = updater.apply(Path(f"{inbox}/agent-config-1.6.0.tar.gz"), man,
                    services_dir=Path(vol), hmac_keys={"1": bytes.fromhex(key)},
                    health_check=lambda: True)
assert res.ok, res.detail
assert (Path(vol) / "agent-config" / "current" / "agentconfig").is_dir(), "agentconfig missing"
print("E2E OK")
PY
echo "PASS"
```

- [ ] **Step 2: 跑冒烟**

Run: `cd /work/chatop && bash station/tests/test_e2e_hotupdate.sh`
Expected: 末行 `PASS`（打包→apply→agentconfig 目录在卷内 current 下就位）

- [ ] **Step 3: 全量单测回归**

Run: `cd /work/chatop && PYTHONPATH=/work/chatop/agent-config python3.11 -m pytest station/tests/ -q`
Expected: 全绿（含原有 station 测试 + 本计划新增）

- [ ] **Step 4: 提交**

```bash
git -C /work/chatop add station/tests/test_e2e_hotupdate.sh
git -C /work/chatop commit -m "test(station): end-to-end hot-update smoke (build->apply->verify)"
```

---

## Self-Review（对照 spec 第 4.1/4.2 节 + P1 行）

**Spec 覆盖：**
- 服务区 + 出厂播种（WANT/cp-an）→ Task 8、Task 10 ✅
- start-station 加载改造（PYTHONPATH/OPENCLAW_TOOL_DIR/station源/StaticFiles 指 current 回退 /opt）→ Task 9（env）+ Task 4/5（web StaticFiles）✅
- bundle 格式 + build-bundle.sh + manifest → Task 7 ✅
- updater apply（验签复用 license HMAC / 原子软链 / 健康门轮询 /dashboard/api/system / 自动回滚）→ Task 2、3、6 ✅
- 本地 inbox + app-manager 市场来源 → Task 6（inbox apply）+ Task 12（fetch）✅
- 大屏 updater 面板 → Task 11 ✅
- station supervisor 支持热重启 → Task 10 ✅

**占位符扫描：** 无 TBD/TODO；每个 code step 均含完整代码。

**类型/命名一致性：** `services.resolve`/`SERVICES_DIR`/`FACTORY_DIR`、`bundle.verify`/`BundleError`、`updater.apply`/`rollback`/`ApplyResult`/`http_health_check`、端点 `/dashboard/api/updater/{versions,apply,rollback}`、manifest 字段 `name/version/sha256/sig/min_base/needs_venv`、服务名四件套——全计划一致。

**已知边界（如实标注）：**
- Task 10 不触发镜像构建（本机 OOM），构建验证归入镜像构建另案（大内存机/经典 builder）。
- `needs_venv=true` 的更新本计划不处理热装 venv（P1 只做纯 Python/静态热更），留后续期。
- 中心下发（B）不在 P1，属 P2/P3。

---

**执行方式（保存后选一）：**
1. **Subagent-Driven（推荐）** — 每任务派新 subagent、任务间双段评审、迭代快。
2. **Inline Execution** — 本会话内按 executing-plans 批量执行 + 检查点。
