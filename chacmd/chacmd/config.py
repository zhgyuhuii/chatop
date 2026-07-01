from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Settings:
    db_url: str
    chayuan_base_url: str
    chayuan_web_url: str
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8767
    api_host: str = "0.0.0.0"
    api_port: int = 8100
    workspace_root: str = "/workspace"

    @staticmethod
    def from_env() -> "Settings":
        return Settings(
            db_url=os.environ.get("CHACMD_DB_URL", "postgresql+asyncpg://chacmd:chacmd@127.0.0.1:5432/chacmd"),
            chayuan_base_url=os.environ.get("CHAYUAN_BASE_URL", "http://127.0.0.1:8000"),
            chayuan_web_url=os.environ.get("CHAYUAN_WEB_URL", "http://127.0.0.1:5173"),
            api_port=int(os.environ.get("CHACMD_API_PORT", "8100")),
            gateway_port=int(os.environ.get("CHACMD_GATEWAY_PORT", "8767")),
        )
