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
