from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

AI_CATEGORIES = {"ai-cli", "ai-runtime", "vscode-ext"}
# gui 分组里属于智能体的例外（OpenHuman 桌面 agent、OpenClaw 配置器不算 agent 但保留发现能力）
AI_GUI_IDS = {"openhuman"}


def load_ai_apps(catalog_path: Path | str) -> list[dict]:
    try:
        data = json.loads(Path(catalog_path).read_text())
    except (OSError, ValueError):
        return []
    return [{"id": a["id"], "name": a.get("name", a["id"]),
             "category": a.get("category", ""), "detect": a.get("detect", "")}
            for a in data.get("apps", [])
            if a.get("category") in AI_CATEGORIES or a.get("id") in AI_GUI_IDS]


def _run_detect(cmd: str) -> bool:
    if not cmd:
        return False
    try:
        return subprocess.run(["bash", "-lc", cmd], capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def detect_installed(apps: list[dict], run: Callable[[str], bool] = _run_detect) -> list[dict]:
    return [{**a, "installed": run(a["detect"])} for a in apps]
