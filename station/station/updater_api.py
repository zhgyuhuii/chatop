"""updater 只读+操作端点，挂在 /dashboard/api/updater/*。"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from . import services, updater
from .bundle import BundleError

_log = logging.getLogger(__name__)

_SERVICE_NAMES = ["station", "agent-config", "dashboard-web", "openclaw-tool"]

_VERSION_RE = re.compile(r"^[\w.-]+$")


def _validate(name: str, version: str = "") -> None:
    if name not in _SERVICE_NAMES:
        raise HTTPException(400, f"未知服务: {name!r}")
    if version and (".." in version or not _VERSION_RE.match(version)):
        raise HTTPException(400, f"非法版本号: {version!r}")


def _services_dir() -> Path:
    """调用期从 env 读服务区（让运行时/测试 setenv 生效），缺省回落模块默认。"""
    return Path(os.environ.get("CHATOP_SERVICES_DIR", str(services.SERVICES_DIR)))


def _inbox() -> Path:
    return Path(os.environ.get("CHATOP_UPDATER_INBOX", str(services.HOME / ".chatop/inbox")))


def _hmac_keys() -> dict:
    """调用期汇总热更验签密钥 → {kid: keybytes}。

    密钥来源两路，互相独立、可同时生效：
    1. 许可密钥文件（CHATOP_LICENSE_KEYS_FILE，缺省回落镜像内 license gate）——
       历史行为，兼容既有部署。
    2. 专用 bundle 签名密钥（CHATOP_BUNDLE_HMAC_KEY，hex 字符串）——
       热更 /apply 的第一公民密钥源，跟 license 闸门是否启用无关；
       license 闸门关闭（生产默认）时，这是唯一还在生效的密钥来源。
    """
    path = Path(os.environ.get("CHATOP_LICENSE_KEYS_FILE", "/opt/chatop/license-keys.json"))
    try:
        cfg = json.loads(path.read_text())
        keys = {str(k): bytes.fromhex(v) for k, v in (cfg.get("hmac_keys") or {}).items()}
    except Exception as e:
        _log.warning("读取许可密钥文件失败 %s: %s（回落 license gate）", path, e)
        try:
            from chatop_license.gate import hmac_keys as _lg
            keys = _lg()
        except Exception as e2:
            _log.warning("回落 license gate 也失败: %s", e2)
            keys = {}

    bundle_key_hex = os.environ.get("CHATOP_BUNDLE_HMAC_KEY")
    if bundle_key_hex:
        try:
            keys = dict(keys)
            keys["bundle"] = bytes.fromhex(bundle_key_hex)
        except ValueError as e:
            _log.warning("CHATOP_BUNDLE_HMAC_KEY 不是合法 hex，已忽略: %s", e)

    return keys


def _active_version(name: str) -> str:
    cur = _services_dir() / name / "current"
    if cur.is_symlink():
        return os.readlink(cur)
    return "factory"


def _factory_dir() -> Path:
    """调用期从 env 读出厂目录，跟 _services_dir() 对称，避免 import 期钉死。"""
    return Path(os.environ.get("CHATOP_FACTORY_DIR", str(services.FACTORY_DIR)))


def _resolve_path(name: str) -> Path:
    """镜像 services.resolve()，但服务区/出厂目录都在调用期读 env——
    跟 _active_version() 用同一份 _services_dir()，避免 runtime 覆盖下两者分家。"""
    cur = _services_dir() / name / "current"
    try:
        if cur.is_dir():
            return cur
    except OSError:
        pass
    return _factory_dir() / name


def create_router() -> APIRouter:
    r = APIRouter(prefix="/dashboard/api/updater")

    @r.get("/versions")
    def versions():
        return {"services": [
            {"name": n, "active": _active_version(n),
             "path": str(_resolve_path(n))}
            for n in _SERVICE_NAMES
        ]}

    @r.post("/apply")
    def apply_bundle(body: dict = Body(...)):
        name = str(body.get("name", ""))
        version = str(body.get("version", ""))
        _validate(name, version)
        man_path = _inbox() / f"{name}-{version}.json"
        tar_path = _inbox() / f"{name}-{version}.tar.gz"
        if not man_path.exists() or not tar_path.exists():
            raise HTTPException(404, f"bundle {name}-{version} not found in inbox")
        try:
            manifest = json.loads(man_path.read_text())
        except (OSError, ValueError) as e:
            raise HTTPException(400, f"manifest 解析失败: {e}")
        if manifest.get("name") != name or manifest.get("version") != version:
            raise HTTPException(400, "manifest 的 name/version 与请求不一致")
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
        _validate(name)
        res = updater.rollback(name, services_dir=_services_dir())
        return {"ok": res.ok, "name": res.name, "version": res.version, "detail": res.detail}

    return r
