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
