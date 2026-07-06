from __future__ import annotations

import os
from pathlib import Path

HOME = Path(os.environ.get("HOME", "/home/admin"))
DATA_DIR = Path(os.environ.get("STATION_DATA_DIR", str(HOME / ".local/share/chatop")))
DB_PATH = DATA_DIR / "station.db"
PORT = int(os.environ.get("STATION_PORT", "8787"))
CATALOG_PATH = Path(os.environ.get("APPS_CATALOG", "/etc/chatop/apps-catalog.json"))
NICKNAME = os.environ.get("STATION_NICKNAME", os.environ.get("HOSTNAME", "workstation"))
WEB_DIR = Path(__file__).parent / "web"
