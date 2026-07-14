"""updater 只读+操作端点，挂在 /dashboard/api/updater/*。"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from . import services, updater
from .bundle import BundleError

_SERVICE_NAMES = ["station", "agent-config", "dashboard-web", "openclaw-tool"]


def _services_dir() -> Path:
    """调用期从 env 读服务区（让运行时/测试 setenv 生效），缺省回落模块默认。"""
    return Path(os.environ.get("CHATOP_SERVICES_DIR", str(services.SERVICES_DIR)))


def _inbox() -> Path:
    return Path(os.environ.get("CHATOP_UPDATER_INBOX", str(services.HOME / ".chatop/inbox")))


def _hmac_keys() -> dict:
    """调用期读许可密钥文件 → {kid: keybytes}；失败回落镜像内 license gate。"""
    path = Path(os.environ.get("CHATOP_LICENSE_KEYS_FILE", "/opt/chatop/license-keys.json"))
    try:
        cfg = json.loads(path.read_text())
        return {str(k): bytes.fromhex(v) for k, v in (cfg.get("hmac_keys") or {}).items()}
    except Exception:
        try:
            from chatop_license.gate import hmac_keys as _lg
            return _lg()
        except Exception:
            return {}


def _active_version(name: str) -> str:
    cur = _services_dir() / name / "current"
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

    @r.post("/apply")
    def apply_bundle(body: dict = Body(...)):
        name = str(body.get("name", ""))
        version = str(body.get("version", ""))
        man_path = _inbox() / f"{name}-{version}.json"
        tar_path = _inbox() / f"{name}-{version}.tar.gz"
        if not man_path.exists() or not tar_path.exists():
            raise HTTPException(404, f"bundle {name}-{version} not found in inbox")
        manifest = json.loads(man_path.read_text())
        health = updater.http_health_check() if body.get("health") != "skip" else (lambda: True)
        try:
            res = updater.apply(tar_path, manifest, services_dir=_services_dir(),
                                hmac_keys=_hmac_keys(), health_check=health)
        except BundleError as e:
            raise HTTPException(400, f"bundle verify failed: {e}")
        return {"ok": res.ok, "name": res.name, "version": res.version, "detail": res.detail}

    @r.post("/rollback")
    def rollback_bundle(body: dict = Body(...)):
        name = str(body.get("name", ""))
        res = updater.rollback(name, services_dir=_services_dir())
        return {"ok": res.ok, "name": res.name, "version": res.version, "detail": res.detail}

    return r
