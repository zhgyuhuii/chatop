from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from typing import Callable

APP_MANAGER = "http://127.0.0.1:8686"

# 打开智能体：会话式/常驻 CLI → 桌面终端（chatop-run-cli）；GUI 型 → app-manager /apps/launch
OPEN_COMMANDS: dict[str, list[str] | None] = {
    "claude-code": ["chatop-run-cli", "claude"],
    "codex": ["chatop-run-cli", "codex"],
    "openclaw": ["chatop-run-cli", "openclaw", "gateway"],
    "hermes": ["chatop-run-cli", "hermes"],
    "openhuman": None,
}

def _openclaw_dir() -> str:
    """openclaw-tool 生效目录：跟随 start-station.sh 导出的 OPENCLAW_TOOL_DIR
    （热更后指向卷内 resolve() 出的当前版本），未设置时回落镜像出厂路径。"""
    return os.environ.get("OPENCLAW_TOOL_DIR", "/opt/openclaw-tool")


def _openclaw_config_cmd() -> list[str]:
    return ["python3.11", f"{_openclaw_dir()}/openclaw_config_gui.py"]


# 打开配置界面：openclaw → openclaw-tool 可视化配置器(tkinter)；hermes → hermes setup；
# claude/codex 配置在其 CLI 内；openhuman 配置在应用内
# openclaw 的值是个可调用对象而非固定 list：必须在调用期（而非 import 期）读
# OPENCLAW_TOOL_DIR，否则热更换了 openclaw-tool 版本后配置器还是打开旧目录的脚本。
CONFIG_COMMANDS: dict[str, list[str] | None | Callable[[], list[str]]] = {
    "openclaw": _openclaw_config_cmd,
    "hermes": ["chatop-run-cli", "hermes", "setup"],
    "claude-code": ["chatop-run-cli", "claude"],
    "codex": ["chatop-run-cli", "codex", "login"],
    "openhuman": None,
}


def _spawn(cmd: list[str]) -> None:
    env = dict(os.environ)
    env["DISPLAY"] = env.get("DISPLAY", ":1") or ":1"
    subprocess.Popen(cmd, env=env, start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(APP_MANAGER + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 固定回环地址
        return json.loads(resp.read() or b"{}")


def _run(table: dict, agent_id: str, spawn: Callable, post: Callable) -> dict:
    if agent_id not in table:
        raise KeyError(f"no action for agent {agent_id}")
    cmd = table[agent_id]
    if callable(cmd):
        cmd = cmd()
    if cmd is None:
        post("/apps/launch", {"id": agent_id})
    else:
        spawn(cmd)
    return {"ok": True, "agent": agent_id}


def open_agent(agent_id: str, spawn: Callable = _spawn, post: Callable = _post) -> dict:
    return _run(OPEN_COMMANDS, agent_id, spawn, post)


def configure_agent(agent_id: str, spawn: Callable = _spawn, post: Callable = _post) -> dict:
    return _run(CONFIG_COMMANDS, agent_id, spawn, post)


def install_agent(agent_id: str, post: Callable = _post) -> dict:
    post("/apps/install", {"id": agent_id})
    return {"ok": True, "agent": agent_id, "state": "queued"}
