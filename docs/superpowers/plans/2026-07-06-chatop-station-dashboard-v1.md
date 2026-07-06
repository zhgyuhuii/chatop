# chatop 工位本地监控大屏 v1（station + dashboard-web）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 spec `2026-07-06-chatop-station-dashboard-design.md` 的 v1：station 常驻服务（探测/任务库/派活/SSE）+ 六区大屏前端（顶栏/A/B/C/D 区）+ 双入口（桌面自启 + Caddy /dashboard）。

**Architecture:** station 是容器内第 4 个常驻服务（FastAPI，127.0.0.1:8787），probe 层只读采集、tasks 层管任务库与 headless 派活、EventHub 扇出 SSE。前端独立 Vite+React，产物由 station serve。统一事件 schema 对齐 ChaCMD（kind/job_id/seq/payload），状态机为其 8 态子集。

**Tech Stack:** Python 3.11 / FastAPI / uvicorn / psutil / sqlite3(stdlib) / pytest+pytest-asyncio+httpx；前端 Vite + React 18 + TypeScript + vitest。

**工作目录:** `/work/chatop`（分支 main）。逐任务 commit **不 bump VERSION**；最后镜像接线任务 bump 一次。push 需 `sudo git push origin main`（root SSH key）。

**测试环境（Task 0 建）:** `<VENV>` = `/tmp/claude-1000/station-venv/bin`。

**已实证的仓库事实（写码前必读）：**
- catalog 镜像内路径 `/etc/chatop/apps-catalog.json`（源码 `app-manager/apps-catalog.json`），条目含 `category`（ai-cli/ai-runtime/vscode-ext）与 `detect`（如 `command -v aider`）。
- app-manager 在 8686；Caddy `forward_auth 127.0.0.1:8686 { uri /auth }` 是统一登录门。
- 浏览器二进制 `/usr/bin/google-chrome-stable`（wrapper 已带 --no-sandbox）。
- Python3.11 在 base 镜像（deadsnakes，含 venv）；系统 python3 是 3.10，station 一律用 python3.11 venv。
- `custom_startup.sh` 由 Dockerfile 第 57 行 printf 生成，末尾 `wait` 不能丢。
- home 播种走 `chatop-seed-home.sh`（`/opt/chatop-seed-home` + WANT 哨兵版本号）。

---

## File Structure

```
station/                          ← 新增（Python 包，仿 agent-bridge 布局）
├─ pyproject.toml
├─ station/
│   ├─ __init__.py  __main__.py  config.py
│   ├─ events.py                  EventHub 扇出 + SSE 格式化
│   ├─ probe/
│   │   ├─ __init__.py
│   │   ├─ catalog.py             已装 AI agent 发现（catalog+detect）
│   │   ├─ agent_probes.py        配置/运行/会话探测（claude-code/codex/openclaw）
│   │   └─ system.py              资源/服务健康/端口/VNC
│   ├─ tasks/
│   │   ├─ __init__.py
│   │   ├─ store.py               SQLite 任务库 + 状态机
│   │   ├─ event_adapter.py       CLI JSONL → 统一事件（claude/codex/openhands）
│   │   ├─ dispatcher.py          headless 派活
│   │   └─ session_watch.py       会话自动侦测
│   └─ api.py                     FastAPI：REST + SSE + 静态
├─ tests/ (test_events.py test_store.py test_adapter.py test_catalog.py
│          test_agent_probes.py test_system.py test_dispatcher.py
│          test_session_watch.py test_api.py)
└─ start-station.sh
dashboard-web/                    ← 新增（Vite+React）
├─ package.json  vite.config.ts  tsconfig.json  index.html
└─ src/ main.tsx App.tsx api.ts streamReducer.ts kpis.ts tokens.css
        components/{TopBar,AgentWall,TaskList,DispatchBox,SystemPanel}.tsx
        streamReducer.test.ts kpis.test.ts
修改: caddy/Caddyfile · Dockerfile · app-manager/chatop-seed-home.sh(WANT=2) · VERSION
```

---

## Task 0: 测试 venv + station 包骨架

**Files:** Create: `station/pyproject.toml`, `station/station/__init__.py`, `station/station/config.py`, `station/tests/__init__.py`（空）

- [ ] **Step 1: 建 venv**

```bash
python3.11 -m venv /tmp/claude-1000/station-venv || python3 -m venv /tmp/claude-1000/station-venv
/tmp/claude-1000/station-venv/bin/pip install -q fastapi 'uvicorn[standard]' psutil pytest pytest-asyncio httpx
```

- [ ] **Step 2: 写包骨架**

`station/pyproject.toml`:
```toml
[project]
name = "station"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = ["fastapi>=0.110,<1", "uvicorn>=0.30,<1", "psutil>=5.9"]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["station*"]
```

`station/station/__init__.py`: 空文件。

`station/station/config.py`:
```python
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
```

- [ ] **Step 3: 提交**

```bash
cd /work/chatop && git add station/ && git commit -m "feat(station): 包骨架+config（工位本地大屏 v1 起步）"
```

## Task 1: EventHub（扇出 + 背压丢最旧 + SSE 格式）

**Files:** Create: `station/station/events.py`；Test: `station/tests/test_events.py`

- [ ] **Step 1: 写失败测试**

```python
import asyncio
import pytest
from station.events import EventHub, sse_format


async def test_publish_reaches_all_subscribers():
    hub = EventHub()
    q1, q2 = hub.subscribe(), hub.subscribe()
    hub.publish({"kind": "progress", "seq": 1})
    assert (await q1.get())["seq"] == 1
    assert (await q2.get())["seq"] == 1


async def test_full_queue_drops_oldest():
    hub = EventHub(maxsize=2)
    q = hub.subscribe()
    for i in range(3):
        hub.publish({"seq": i})
    assert (await q.get())["seq"] == 1  # seq0 被丢
    assert (await q.get())["seq"] == 2


async def test_unsubscribe_stops_delivery():
    hub = EventHub()
    q = hub.subscribe()
    hub.unsubscribe(q)
    hub.publish({"seq": 1})
    assert q.empty()


def test_sse_format():
    assert sse_format({"a": 1}) == 'data: {"a": 1}\n\n'
```

- [ ] **Step 2: 跑测确认失败** `cd /work/chatop/station && /tmp/claude-1000/station-venv/bin/python -m pytest tests/test_events.py -q` → ImportError
- [ ] **Step 3: 实现**

```python
from __future__ import annotations

import asyncio
import json


class EventHub:
    """进程内事件扇出（ChaCMD EventStreamHub 手法：满则丢最旧，不阻塞发布方）。"""

    def __init__(self, maxsize: int = 256) -> None:
        self._subs: set[asyncio.Queue] = set()
        self._maxsize = maxsize

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, event: dict) -> None:
        for q in list(self._subs):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(event)


def sse_format(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
```

- [ ] **Step 4: 跑测通过**
- [ ] **Step 5: 提交** `git add station/ && git commit -m "feat(station): EventHub 扇出+背压丢最旧+SSE 格式"`

## Task 2: 任务库 TaskStore（SQLite + 状态机）

**Files:** Create: `station/station/tasks/__init__.py`（空）, `station/station/tasks/store.py`；Test: `station/tests/test_store.py`

- [ ] **Step 1: 写失败测试**

```python
import pytest
from station.tasks.store import TaskStore, TERMINAL


def _store(tmp_path):
    return TaskStore(tmp_path / "t.db")


def test_create_and_get(tmp_path):
    s = _store(tmp_path)
    job = s.create_job("claude-code", "fix bug", "/tmp/w")
    got = s.get_job(job["id"])
    assert got["agent"] == "claude-code" and got["state"] == "queued"
    assert got["source"] == "manual"


def test_legal_transition_chain(tmp_path):
    s = _store(tmp_path)
    j = s.create_job("codex", "g", None)
    s.transition(j["id"], "running")
    s.transition(j["id"], "succeeded")
    assert s.get_job(j["id"])["state"] == "succeeded"


def test_illegal_transition_raises(tmp_path):
    s = _store(tmp_path)
    j = s.create_job("codex", "g", None)
    with pytest.raises(ValueError):
        s.transition(j["id"], "succeeded")  # queued 不能直达终态


def test_step_tokens_and_events(tmp_path):
    s = _store(tmp_path)
    j = s.create_job("codex", "g", None)
    s.set_step(j["id"], "editing auth.js")
    s.add_tokens(j["id"], 120)
    s.append_event({"job_id": j["id"], "seq": 0, "kind": "progress", "payload": {"a": 1}, "ts": 1.0})
    got = s.get_job(j["id"])
    assert got["current_step"] == "editing auth.js" and got["tokens"] == 120
    assert s.list_events(j["id"])[0]["payload"] == {"a": 1}


def test_upsert_detected_idempotent(tmp_path):
    s = _store(tmp_path)
    s.upsert_detected("detected-claude-abc", "claude-code", "sess-1", "running")
    s.upsert_detected("detected-claude-abc", "claude-code", "sess-1", "succeeded")
    jobs = s.list_jobs()
    assert len(jobs) == 1 and jobs[0]["state"] == "succeeded" and jobs[0]["source"] == "detected"
```

- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现**

```python
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path

STATES = {"queued", "running", "pending_approval", "succeeded", "failed", "cancelled"}
TERMINAL = {"succeeded", "failed", "cancelled"}
_ALLOWED = {
    "queued": {"running", "cancelled"},
    "running": {"pending_approval", "succeeded", "failed", "cancelled"},
    "pending_approval": {"running", "cancelled"},
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
  id TEXT PRIMARY KEY, agent TEXT NOT NULL, goal TEXT NOT NULL,
  workdir TEXT, source TEXT NOT NULL DEFAULT 'manual',
  state TEXT NOT NULL DEFAULT 'queued', current_step TEXT DEFAULT '',
  tokens INTEGER DEFAULT 0, created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS job_events(
  rid INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
  seq INTEGER, kind TEXT, payload TEXT, ts REAL);
CREATE INDEX IF NOT EXISTS ix_events_job ON job_events(job_id);
"""


class TaskStore:
    def __init__(self, db_path: Path | str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(_SCHEMA)

    def create_job(self, agent: str, goal: str, workdir: str | None,
                   source: str = "manual", job_id: str | None = None) -> dict:
        jid = job_id or uuid.uuid4().hex[:12]
        now = time.time()
        self._db.execute(
            "INSERT INTO jobs(id,agent,goal,workdir,source,state,created_at,updated_at)"
            " VALUES(?,?,?,?,?,'queued',?,?)", (jid, agent, goal, workdir, source, now, now))
        self._db.commit()
        return self.get_job(jid)

    def get_job(self, job_id: str) -> dict:
        row = self._db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return dict(row)

    def list_jobs(self, limit: int = 200) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def transition(self, job_id: str, new_state: str) -> None:
        cur = self.get_job(job_id)["state"]
        if new_state not in _ALLOWED.get(cur, set()):
            raise ValueError(f"illegal transition {cur} -> {new_state}")
        self._db.execute("UPDATE jobs SET state=?, updated_at=? WHERE id=?",
                         (new_state, time.time(), job_id))
        self._db.commit()

    def set_step(self, job_id: str, step: str) -> None:
        self._db.execute("UPDATE jobs SET current_step=?, updated_at=? WHERE id=?",
                         (step[:200], time.time(), job_id))
        self._db.commit()

    def add_tokens(self, job_id: str, n: int) -> None:
        self._db.execute("UPDATE jobs SET tokens=tokens+?, updated_at=? WHERE id=?",
                         (n, time.time(), job_id))
        self._db.commit()

    def append_event(self, ev: dict) -> None:
        self._db.execute(
            "INSERT INTO job_events(job_id,seq,kind,payload,ts) VALUES(?,?,?,?,?)",
            (ev["job_id"], ev.get("seq", 0), ev.get("kind", "progress"),
             json.dumps(ev.get("payload", {}), ensure_ascii=False), ev.get("ts", time.time())))
        self._db.commit()

    def list_events(self, job_id: str, limit: int = 500) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM job_events WHERE job_id=? ORDER BY rid LIMIT ?",
            (job_id, limit)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d["payload"] or "{}")
            out.append(d)
        return out

    def upsert_detected(self, job_id: str, agent: str, goal: str, state: str) -> None:
        """侦测型任务：允许直接落任意状态（历史会话无从走状态机）。"""
        now = time.time()
        self._db.execute(
            "INSERT INTO jobs(id,agent,goal,workdir,source,state,created_at,updated_at)"
            " VALUES(?,?,?,NULL,'detected',?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET state=excluded.state, updated_at=excluded.updated_at",
            (job_id, agent, goal, state, now, now))
        self._db.commit()
```

- [ ] **Step 4: 跑测通过**
- [ ] **Step 5: 提交** `git commit -m "feat(station): SQLite 任务库+ChaCMD 8态子集状态机"`

## Task 3: 事件适配器（claude / codex / openhands JSONL → 统一事件）

**Files:** Create: `station/station/tasks/event_adapter.py`；Test: `station/tests/test_adapter.py`

- [ ] **Step 1: 写失败测试**

```python
import json
from station.tasks.event_adapter import claude_line_to_event, codex_line_to_event, PARSERS


def test_claude_result_success_maps_succeeded_with_tokens():
    line = json.dumps({"type": "result", "subtype": "success", "is_error": False,
                       "result": "done", "usage": {"input_tokens": 10, "output_tokens": 5}})
    ev = claude_line_to_event(line, "j1", "ws", 3)
    assert ev["kind"] == "succeeded" and ev["seq"] == 3 and ev["job_id"] == "j1"
    assert ev["payload"]["tokens"] == 15


def test_claude_error_result_maps_failed():
    line = json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True})
    assert claude_line_to_event(line, "j", "ws", 0)["kind"] == "failed"


def test_claude_assistant_maps_progress_with_text():
    line = json.dumps({"type": "assistant",
                       "message": {"content": [{"type": "text", "text": "editing file"}]}})
    ev = claude_line_to_event(line, "j", "ws", 1)
    assert ev["kind"] == "progress" and ev["payload"]["text"] == "editing file"


def test_codex_task_complete_maps_succeeded():
    line = json.dumps({"id": "0", "msg": {"type": "task_complete"}})
    assert codex_line_to_event(line, "j", "ws", 0)["kind"] == "succeeded"


def test_codex_error_maps_failed():
    line = json.dumps({"msg": {"type": "error", "message": "boom"}})
    assert codex_line_to_event(line, "j", "ws", 0)["kind"] == "failed"


def test_garbage_line_is_progress_raw():
    ev = claude_line_to_event("not json", "j", "ws", 0)
    assert ev["kind"] == "progress" and ev["payload"]["raw"] == "not json"


def test_parsers_registry():
    assert set(PARSERS) >= {"claude-code", "codex"}
```

- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现**

```python
from __future__ import annotations

import json
import time
from typing import Any

# 统一事件 schema 对齐 ChaCMD：job_id/container/kind/seq/payload/ts。
# kind: progress | succeeded | failed


def _base(job_id: str, nickname: str, seq: int, kind: str, payload: dict) -> dict[str, Any]:
    return {"job_id": job_id, "container": nickname, "kind": kind,
            "seq": seq, "payload": payload, "ts": time.time()}


def _loads(line: str) -> dict | None:
    try:
        obj = json.loads(line)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def claude_line_to_event(line: str, job_id: str, nickname: str, seq: int) -> dict:
    """claude -p --output-format stream-json --verbose 的 JSONL。"""
    obj = _loads(line)
    if obj is None:
        return _base(job_id, nickname, seq, "progress", {"raw": line})
    t = obj.get("type")
    if t == "result":
        ok = not obj.get("is_error") and obj.get("subtype") == "success"
        usage = obj.get("usage") or {}
        tokens = int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))
        payload = {"result": obj.get("result", ""), "tokens": tokens}
        return _base(job_id, nickname, seq, "succeeded" if ok else "failed", payload)
    if t == "assistant":
        content = (obj.get("message") or {}).get("content") or []
        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        return _base(job_id, nickname, seq, "progress", {"text": " ".join(texts)[:500]})
    return _base(job_id, nickname, seq, "progress", {"type": t})


def codex_line_to_event(line: str, job_id: str, nickname: str, seq: int) -> dict:
    """codex exec --json 的 JSONL（{"msg":{"type":...}}）。"""
    obj = _loads(line)
    if obj is None:
        return _base(job_id, nickname, seq, "progress", {"raw": line})
    msg = obj.get("msg") or {}
    t = msg.get("type", "")
    if t == "task_complete":
        return _base(job_id, nickname, seq, "succeeded", {k: v for k, v in msg.items() if k != "type"})
    if t == "error":
        return _base(job_id, nickname, seq, "failed", {"message": msg.get("message", "")})
    return _base(job_id, nickname, seq, "progress", {"type": t, "text": str(msg.get("message", ""))[:500]})


def openhands_line_to_event(line: str, job_id: str, nickname: str, seq: int) -> dict:
    """OpenHands JSONL（保留 agent-bridge 原映射，供将来常驻 runtime 用）。"""
    obj = _loads(line)
    if obj is None:
        return _base(job_id, nickname, seq, "progress", {"raw": line})
    action = obj.get("action")
    kind = {"finish": "succeeded", "error": "failed"}.get(action, "progress")
    payload: dict[str, Any] = {"action": action} if action else {}
    payload.update({k: v for k, v in obj.items() if k != "action"})
    return _base(job_id, nickname, seq, kind, payload)


PARSERS = {"claude-code": claude_line_to_event, "codex": codex_line_to_event,
           "openhands": openhands_line_to_event}
```

- [ ] **Step 4: 跑测通过**
- [ ] **Step 5: 提交** `git commit -m "feat(station): claude/codex/openhands JSONL→统一事件适配器"`

## Task 4: 已装 agent 发现（catalog + detect）

**Files:** Create: `station/station/probe/__init__.py`（空）, `station/station/probe/catalog.py`；Test: `station/tests/test_catalog.py`

- [ ] **Step 1: 写失败测试**

```python
import json
from station.probe.catalog import load_ai_apps, detect_installed

CATALOG = {"version": 1, "apps": [
    {"id": "claude-code", "name": "Claude Code", "category": "ai-cli", "detect": "command -v claude"},
    {"id": "openclaw", "name": "OpenClaw", "category": "ai-runtime", "detect": "command -v openclaw"},
    {"id": "gimp", "name": "GIMP", "category": "proot-gui", "detect": "command -v gimp"},
]}


def test_load_filters_ai_categories(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps(CATALOG))
    apps = load_ai_apps(p)
    assert [a["id"] for a in apps] == ["claude-code", "openclaw"]


def test_detect_installed_marks_flag(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps(CATALOG))
    apps = detect_installed(load_ai_apps(p), run=lambda cmd: "claude" in cmd)
    by = {a["id"]: a["installed"] for a in apps}
    assert by == {"claude-code": True, "openclaw": False}


def test_missing_catalog_returns_empty(tmp_path):
    assert load_ai_apps(tmp_path / "nope.json") == []
```

- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现**

```python
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

AI_CATEGORIES = {"ai-cli", "ai-runtime", "vscode-ext"}


def load_ai_apps(catalog_path: Path | str) -> list[dict]:
    try:
        data = json.loads(Path(catalog_path).read_text())
    except (OSError, ValueError):
        return []
    return [{"id": a["id"], "name": a.get("name", a["id"]),
             "category": a.get("category", ""), "detect": a.get("detect", "")}
            for a in data.get("apps", []) if a.get("category") in AI_CATEGORIES]


def _run_detect(cmd: str) -> bool:
    if not cmd:
        return False
    try:
        return subprocess.run(["bash", "-lc", cmd], capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def detect_installed(apps: list[dict], run: Callable[[str], bool] = _run_detect) -> list[dict]:
    return [{**a, "installed": run(a["detect"])} for a in apps]
```

- [ ] **Step 4: 跑测通过**
- [ ] **Step 5: 提交** `git commit -m "feat(station): catalog AI 分组+detect 已装发现"`

## Task 5: agent 探测器（配置/运行/会话）

**Files:** Create: `station/station/probe/agent_probes.py`；Test: `station/tests/test_agent_probes.py`

- [ ] **Step 1: 写失败测试**

```python
import json
import time
from station.probe.agent_probes import AGENT_SPECS, probe_agent


def _mk_home(tmp_path):
    (tmp_path / ".claude" / "projects" / "p1").mkdir(parents=True)
    (tmp_path / ".claude.json").write_text(json.dumps({"model": "opus"}))
    return tmp_path


def test_configured_when_candidate_exists(tmp_path):
    home = _mk_home(tmp_path)
    st = probe_agent("claude-code", AGENT_SPECS["claude-code"], home, procs=[])
    assert st["configured"] is True and st["model"] == "opus"


def test_not_configured_when_no_files(tmp_path):
    st = probe_agent("codex", AGENT_SPECS["codex"], tmp_path, procs=[])
    assert st["configured"] is False and st["model"] == ""


def test_runtime_running_via_proc_match(tmp_path):
    procs = [{"pid": 9, "name": "openclaw", "cmdline": "openclaw serve", "cpu": 1.5, "mem_mb": 80.0}]
    st = probe_agent("openclaw", AGENT_SPECS["openclaw"], tmp_path, procs=procs)
    assert st["running"] is True and st["cpu"] == 1.5 and st["mem_mb"] == 80.0


def test_session_activity_counts_recent_files(tmp_path):
    home = _mk_home(tmp_path)
    f = home / ".claude" / "projects" / "p1" / "s1.jsonl"
    f.write_text("{}")
    st = probe_agent("claude-code", AGENT_SPECS["claude-code"], home, procs=[], now=time.time())
    assert st["active_sessions"] == 1 and st["last_active"] > 0
```

- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现**

```python
from __future__ import annotations

import json
import re
import time
from pathlib import Path

# type: runtime=常驻进程 | session=会话式 CLI | human=人工桌面型（v1.5 上屏）
AGENT_SPECS: dict[str, dict] = {
    "claude-code": {"type": "session", "proc_match": "claude",
                    "config_candidates": [".claude.json", ".claude/settings.json"],
                    "session_glob": ".claude/projects/*/*.jsonl"},
    "codex": {"type": "session", "proc_match": "codex",
              "config_candidates": [".codex/auth.json", ".codex/config.toml"],
              "session_glob": ".codex/sessions/**/*.jsonl"},
    "openclaw": {"type": "runtime", "proc_match": "openclaw",
                 "config_candidates": [".openclaw/openclaw.json", ".config/openclaw/config.json"],
                 "session_glob": None},
}
_FRESH_S = 900  # 15min 内活动的会话算 active


def _read_model(path: Path) -> str:
    try:
        text = path.read_text()
    except OSError:
        return ""
    if path.suffix == ".json":
        try:
            return str(json.loads(text).get("model", ""))
        except ValueError:
            return ""
    m = re.search(r'^\s*model\s*=\s*"([^"]+)"', text, re.M)  # toml
    return m.group(1) if m else ""


def probe_agent(agent_id: str, spec: dict, home: Path, procs: list[dict],
                now: float | None = None) -> dict:
    now = now or time.time()
    configured, model = False, ""
    for rel in spec["config_candidates"]:
        p = home / rel
        if p.is_file() and p.stat().st_size > 0:
            configured = True
            model = model or _read_model(p)
    matched = [p for p in procs if spec["proc_match"] in (p.get("name", "") + " " + p.get("cmdline", ""))]
    active, last = 0, 0.0
    if spec.get("session_glob"):
        for f in home.glob(spec["session_glob"]):
            try:
                mt = f.stat().st_mtime
            except OSError:
                continue
            last = max(last, mt)
            if now - mt < _FRESH_S:
                active += 1
    return {"id": agent_id, "agent_type": spec["type"], "configured": configured, "model": model,
            "running": bool(matched), "active_sessions": active, "last_active": last,
            "cpu": round(sum(p.get("cpu", 0.0) for p in matched), 1),
            "mem_mb": round(sum(p.get("mem_mb", 0.0) for p in matched), 1)}
```

- [ ] **Step 4: 跑测通过**
- [ ] **Step 5: 提交** `git commit -m "feat(station): claude/codex/openclaw 配置·运行·会话探测器"`

## Task 6: 系统探测（资源/服务健康/端口）

**Files:** Create: `station/station/probe/system.py`；Test: `station/tests/test_system.py`

- [ ] **Step 1: 写失败测试**

```python
from station.probe.system import snapshot, list_procs, SERVICES


def test_snapshot_service_health_from_procs():
    procs = [{"pid": 1, "name": "Xvnc", "cmdline": "/usr/bin/Xvnc :1"},
             {"pid": 2, "name": "caddy", "cmdline": "caddy run"},
             {"pid": 3, "name": "python3", "cmdline": "python3 /usr/local/lib/chatop/app_manager.py"}]
    snap = snapshot(procs=procs, res={"cpu": 10.0, "mem": 40.0, "disk": 50.0, "uptime": 99.0},
                    ports=[7443, 8686], established=set())
    svc = {s["name"]: s["ok"] for s in snap["services"]}
    assert svc["Xvnc"] and svc["caddy"] and svc["app-manager"]
    assert not svc["filebrowser"] and not svc["station"]
    assert snap["cpu"] == 10.0 and 7443 in snap["ports"]


def test_vnc_online_from_established():
    snap = snapshot(procs=[], res={"cpu": 0, "mem": 0, "disk": 0, "uptime": 0},
                    ports=[], established={6901})
    assert snap["vnc_online"] is True


def test_list_procs_returns_dicts():
    procs = list_procs()
    assert isinstance(procs, list)
    assert all("pid" in p and "cmdline" in p for p in procs[:3])
```

- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现**

```python
from __future__ import annotations

import time

import psutil

SERVICES = [("Xvnc", "Xvnc"), ("caddy", "caddy"), ("app-manager", "app_manager.py"),
            ("filebrowser", "filebrowser"), ("station", "station")]


def list_procs() -> list[dict]:
    out = []
    for p in psutil.process_iter(["pid", "name", "cmdline", "cpu_percent", "memory_info"]):
        try:
            info = p.info
            out.append({"pid": info["pid"], "name": info["name"] or "",
                        "cmdline": " ".join(info["cmdline"] or []),
                        "cpu": info["cpu_percent"] or 0.0,
                        "mem_mb": round((info["memory_info"].rss if info["memory_info"] else 0) / 1e6, 1)})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out


def _live_res() -> dict:
    return {"cpu": psutil.cpu_percent(interval=None),
            "mem": psutil.virtual_memory().percent,
            "disk": psutil.disk_usage("/").percent,
            "uptime": time.time() - psutil.boot_time()}


def _live_ports_established() -> tuple[list[int], set[int]]:
    ports, est = [], set()
    try:
        for c in psutil.net_connections(kind="tcp"):
            if c.status == psutil.CONN_LISTEN and c.laddr:
                ports.append(c.laddr.port)
            elif c.status == psutil.CONN_ESTABLISHED and c.laddr:
                est.add(c.laddr.port)
    except psutil.AccessDenied:
        pass
    return sorted(set(ports)), est


def snapshot(procs: list[dict] | None = None, res: dict | None = None,
             ports: list[int] | None = None, established: set[int] | None = None) -> dict:
    procs = list_procs() if procs is None else procs
    res = _live_res() if res is None else res
    if ports is None or established is None:
        ports, established = _live_ports_established()
    services = [{"name": name, "ok": any(match in (p["name"] + " " + p["cmdline"]) for p in procs)}
                for name, match in SERVICES]
    return {**res, "services": services, "ports": ports,
            "vnc_online": bool({6901, 7443} & established), "ts": time.time()}
```

- [ ] **Step 4: 跑测通过**
- [ ] **Step 5: 提交** `git commit -m "feat(station): 系统资源/服务健康/端口/VNC 探测"`

## Task 7: Dispatcher（headless 派活 + 流式事件）

**Files:** Create: `station/station/tasks/dispatcher.py`；Test: `station/tests/test_dispatcher.py`

- [ ] **Step 1: 写失败测试**（fake CLI 用 python 内联脚本吐 claude 风格 JSONL）

```python
import asyncio
import json
import sys
import pytest
from station.events import EventHub
from station.tasks.dispatcher import Dispatcher
from station.tasks.store import TaskStore

FAKE_OK = [sys.executable, "-c", (
    "import json;"
    "print(json.dumps({'type':'assistant','message':{'content':[{'type':'text','text':'step1'}]}}));"
    "print(json.dumps({'type':'result','subtype':'success','is_error':False,'result':'done',"
    "'usage':{'input_tokens':7,'output_tokens':3}}))")]
FAKE_FAIL = [sys.executable, "-c", "import sys; sys.exit(2)"]


async def _wait_terminal(store, jid, timeout=5.0):
    for _ in range(int(timeout / 0.05)):
        if store.get_job(jid)["state"] in {"succeeded", "failed", "cancelled"}:
            return store.get_job(jid)
        await asyncio.sleep(0.05)
    raise TimeoutError


async def test_dispatch_success_flow(tmp_path):
    store, hub = TaskStore(tmp_path / "t.db"), EventHub()
    q = hub.subscribe()
    d = Dispatcher(store, hub, commands={"claude-code": lambda goal: FAKE_OK})
    jid = await d.dispatch("claude-code", "do it", str(tmp_path))
    job = await _wait_terminal(store, jid)
    assert job["state"] == "succeeded" and job["tokens"] == 10
    assert job["current_step"] == "step1"
    kinds = [q.get_nowait()["kind"] for _ in range(q.qsize())]
    assert "succeeded" in kinds
    assert store.list_events(jid)


async def test_dispatch_nonzero_exit_without_result_is_failed(tmp_path):
    store, hub = TaskStore(tmp_path / "t.db"), EventHub()
    d = Dispatcher(store, hub, commands={"codex": lambda goal: FAKE_FAIL})
    jid = await d.dispatch("codex", "boom", None)
    assert (await _wait_terminal(store, jid))["state"] == "failed"


async def test_dispatch_unknown_agent_raises(tmp_path):
    d = Dispatcher(TaskStore(tmp_path / "t.db"), EventHub(), commands={})
    with pytest.raises(KeyError):
        await d.dispatch("nope", "g", None)
```

- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现**

```python
from __future__ import annotations

import asyncio
import time
from typing import Callable

from ..events import EventHub
from .event_adapter import PARSERS, claude_line_to_event
from .store import TaskStore, TERMINAL

# 无头派活命令表。容器即工位（单用户已隔离），跳过交互确认是有意为之。
AGENT_COMMANDS: dict[str, Callable[[str], list[str]]] = {
    "claude-code": lambda goal: ["claude", "-p", goal, "--output-format", "stream-json",
                                 "--verbose", "--dangerously-skip-permissions"],
    "codex": lambda goal: ["codex", "exec", "--full-auto", "--json", goal],
}


class Dispatcher:
    def __init__(self, store: TaskStore, hub: EventHub, nickname: str = "workstation",
                 commands: dict | None = None, parsers: dict | None = None) -> None:
        self._store, self._hub, self._nick = store, hub, nickname
        self._commands = AGENT_COMMANDS if commands is None else commands
        self._parsers = PARSERS if parsers is None else parsers

    async def dispatch(self, agent: str, goal: str, workdir: str | None) -> str:
        if agent not in self._commands:
            raise KeyError(f"agent {agent} not dispatchable")
        job = self._store.create_job(agent, goal, workdir)
        asyncio.get_running_loop().create_task(self._run(job))
        return job["id"]

    def _emit(self, ev: dict) -> None:
        self._store.append_event(ev)
        self._hub.publish(ev)

    async def _run(self, job: dict) -> None:
        jid, agent = job["id"], job["agent"]
        parse = self._parsers.get(agent, claude_line_to_event)
        self._store.transition(jid, "running")
        self._emit({"job_id": jid, "container": self._nick, "kind": "progress",
                    "seq": 0, "payload": {"text": "started", "agent": agent}, "ts": time.time()})
        try:
            proc = await asyncio.create_subprocess_exec(
                *self._commands[agent](job["goal"]), cwd=job["workdir"] or None,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        except OSError as e:
            self._store.transition(jid, "failed")
            self._emit({"job_id": jid, "container": self._nick, "kind": "failed",
                        "seq": 1, "payload": {"message": f"spawn failed: {e}"}, "ts": time.time()})
            return
        seq, final = 1, None
        assert proc.stdout is not None
        while True:
            raw = await proc.stdout.readline()
            if not raw:
                break
            ev = parse(raw.decode(errors="replace").rstrip("\n"), jid, self._nick, seq)
            seq += 1
            self._emit(ev)
            p = ev.get("payload", {})
            if p.get("text"):
                self._store.set_step(jid, p["text"])
            if p.get("tokens"):
                self._store.add_tokens(jid, int(p["tokens"]))
            if ev["kind"] in TERMINAL:
                final = ev["kind"]
        rc = await proc.wait()
        state = final or ("succeeded" if rc == 0 else "failed")
        if self._store.get_job(jid)["state"] not in TERMINAL:
            self._store.transition(jid, state)
        if final is None:
            self._emit({"job_id": jid, "container": self._nick, "kind": state,
                        "seq": seq, "payload": {"exit_code": rc}, "ts": time.time()})
```

- [ ] **Step 4: 跑测通过**
- [ ] **Step 5: 提交** `git commit -m "feat(station): headless 派活 dispatcher（流式事件+终态判定）"`

## Task 8: 会话自动侦测 session_watch

**Files:** Create: `station/station/tasks/session_watch.py`；Test: `station/tests/test_session_watch.py`

- [ ] **Step 1: 写失败测试**

```python
import json
import os
import time
from station.tasks.session_watch import scan_sessions
from station.tasks.store import TaskStore


def _mk(home, rel, lines, age_s):
    f = home / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("\n".join(lines))
    t = time.time() - age_s
    os.utime(f, (t, t))
    return f


def test_fresh_session_becomes_running_task(tmp_path):
    _mk(tmp_path, ".claude/projects/p/s1.jsonl", ["{}"], age_s=10)
    store = TaskStore(tmp_path / "t.db")
    scan_sessions(tmp_path, store)
    jobs = store.list_jobs()
    assert len(jobs) == 1 and jobs[0]["state"] == "running" and jobs[0]["source"] == "detected"


def test_stale_session_with_success_result_is_succeeded(tmp_path):
    line = json.dumps({"type": "result", "subtype": "success", "is_error": False})
    _mk(tmp_path, ".claude/projects/p/s2.jsonl", ["{}", line], age_s=3600)
    store = TaskStore(tmp_path / "t.db")
    scan_sessions(tmp_path, store)
    assert store.list_jobs()[0]["state"] == "succeeded"


def test_stale_unparseable_session_is_skipped(tmp_path):
    _mk(tmp_path, ".claude/projects/p/s3.jsonl", ["garbage"], age_s=3600)
    store = TaskStore(tmp_path / "t.db")
    scan_sessions(tmp_path, store)
    assert store.list_jobs() == []


def test_scan_is_idempotent(tmp_path):
    _mk(tmp_path, ".claude/projects/p/s1.jsonl", ["{}"], age_s=10)
    store = TaskStore(tmp_path / "t.db")
    scan_sessions(tmp_path, store)
    scan_sessions(tmp_path, store)
    assert len(store.list_jobs()) == 1
```

- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现**

```python
from __future__ import annotations

import hashlib
import time
from pathlib import Path

from ..probe.agent_probes import AGENT_SPECS
from .event_adapter import PARSERS
from .store import TaskStore

_FRESH_S = 180      # 3min 内有写入 → 认为会话进行中
_MAX_AGE_S = 86400  # 只看 24h 内的会话


def scan_sessions(home: Path, store: TaskStore, now: float | None = None) -> None:
    now = now or time.time()
    for agent_id, spec in AGENT_SPECS.items():
        glob = spec.get("session_glob")
        if not glob:
            continue
        parse = PARSERS.get(agent_id)
        for f in home.glob(glob):
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            age = now - mtime
            if age > _MAX_AGE_S:
                continue
            jid = f"detected-{agent_id}-{hashlib.sha1(str(f).encode()).hexdigest()[:12]}"
            if age < _FRESH_S:
                store.upsert_detected(jid, agent_id, f.stem, "running")
                continue
            state = None
            if parse:
                try:
                    lines = f.read_text(errors="replace").strip().splitlines()
                except OSError:
                    continue
                if lines:
                    kind = parse(lines[-1], jid, "detected", 0)["kind"]
                    if kind in ("succeeded", "failed"):
                        state = kind
            if state:  # 结局不可判的陈旧会话不入库（诚实优先）
                store.upsert_detected(jid, agent_id, f.stem, state)
```

- [ ] **Step 4: 跑测通过**
- [ ] **Step 5: 提交** `git commit -m "feat(station): 会话自动侦测→侦测型任务（新鲜=running/陈旧按末行判终态）"`

## Task 9: FastAPI 应用（REST + SSE + 静态）

**Files:** Create: `station/station/api.py`, `station/station/__main__.py`；Test: `station/tests/test_api.py`

- [ ] **Step 1: 写失败测试**

```python
import asyncio
import json
import sys
import httpx
import pytest
from station.api import create_app
from station.events import EventHub
from station.tasks.dispatcher import Dispatcher
from station.tasks.store import TaskStore

FAKE_OK = [sys.executable, "-c",
           "import json; print(json.dumps({'type':'result','subtype':'success','is_error':False}))"]


def _app(tmp_path):
    store, hub = TaskStore(tmp_path / "t.db"), EventHub()
    disp = Dispatcher(store, hub, commands={"claude-code": lambda g: FAKE_OK})
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"apps": [
        {"id": "claude-code", "name": "Claude Code", "category": "ai-cli", "detect": "true"}]}))
    return create_app(store, hub, disp, home=tmp_path, catalog_path=catalog), store, hub


async def test_agents_endpoint(tmp_path):
    app, *_ = _app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/dashboard/api/agents")
    assert r.status_code == 200
    agents = r.json()
    assert agents[0]["id"] == "claude-code" and "configured" in agents[0]


async def test_dispatch_and_tasks(tmp_path):
    app, store, _ = _app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/dashboard/api/dispatch", json={"agent": "claude-code", "goal": "hi"})
        assert r.status_code == 200
        jid = r.json()["job_id"]
        for _ in range(50):
            if store.get_job(jid)["state"] == "succeeded":
                break
            await asyncio.sleep(0.05)
        r2 = await c.get("/dashboard/api/tasks")
        assert any(t["id"] == jid for t in r2.json())
        r3 = await c.get(f"/dashboard/api/tasks/{jid}/events")
        assert r3.status_code == 200 and isinstance(r3.json(), list)


async def test_dispatch_unknown_agent_400(tmp_path):
    app, *_ = _app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.post("/dashboard/api/dispatch", json={"agent": "nope", "goal": "g"})
    assert r.status_code == 400


async def test_system_endpoint(tmp_path):
    app, *_ = _app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/dashboard/api/system")
    snap = r.json()
    assert "cpu" in snap and "services" in snap


async def test_sse_stream_delivers_published_event(tmp_path):
    app, _, hub = _app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        async with c.stream("GET", "/dashboard/api/events") as resp:
            hub.publish({"kind": "progress", "seq": 1, "job_id": "j"})
            async for chunk in resp.aiter_text():
                if chunk.strip():
                    assert '"seq": 1' in chunk
                    break
```

- [ ] **Step 2: 跑测确认失败**
- [ ] **Step 3: 实现**

`station/station/api.py`:
```python
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .events import EventHub, sse_format
from .probe.agent_probes import AGENT_SPECS, probe_agent
from .probe.catalog import detect_installed, load_ai_apps
from .probe.system import list_procs, snapshot
from .tasks.dispatcher import Dispatcher
from .tasks.session_watch import scan_sessions
from .tasks.store import TaskStore


class DispatchReq(BaseModel):
    agent: str
    goal: str
    workdir: str | None = None


def create_app(store: TaskStore, hub: EventHub, dispatcher: Dispatcher,
               home: Path | None = None, catalog_path: Path | None = None,
               web_dir: Path | None = None) -> FastAPI:
    home = home or config.HOME
    catalog_path = catalog_path or config.CATALOG_PATH
    app = FastAPI(title="chatop station")

    @app.get("/dashboard/api/agents")
    def agents() -> list[dict]:
        procs = list_procs()
        out = []
        for a in detect_installed(load_ai_apps(catalog_path)):
            st = (probe_agent(a["id"], AGENT_SPECS[a["id"]], home, procs)
                  if a["installed"] and a["id"] in AGENT_SPECS else {})
            out.append({**a, **st, "dispatchable": a["id"] in dispatcher._commands})
        return out

    @app.get("/dashboard/api/tasks")
    def tasks() -> list[dict]:
        scan_sessions(home, store)
        return store.list_jobs()

    @app.get("/dashboard/api/tasks/{job_id}/events")
    def task_events(job_id: str) -> list[dict]:
        try:
            store.get_job(job_id)
        except KeyError:
            raise HTTPException(404, "no such job")
        return store.list_events(job_id)

    @app.post("/dashboard/api/dispatch")
    async def dispatch(req: DispatchReq) -> dict:
        try:
            jid = await dispatcher.dispatch(req.agent, req.goal, req.workdir)
        except KeyError as e:
            raise HTTPException(400, str(e))
        return {"job_id": jid}

    @app.get("/dashboard/api/system")
    def system() -> dict:
        return snapshot()

    @app.get("/dashboard/api/events")
    async def events() -> StreamingResponse:
        q = hub.subscribe()

        async def gen():
            try:
                yield ": connected\n\n"
                while True:
                    yield sse_format(await q.get())
            finally:
                hub.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    wd = web_dir or config.WEB_DIR
    if wd.is_dir():  # 前端产物存在才挂（后端单测不需要）
        app.mount("/dashboard", StaticFiles(directory=str(wd), html=True), name="web")
    return app
```

`station/station/__main__.py`:
```python
import uvicorn

from . import config
from .api import create_app
from .events import EventHub
from .tasks.dispatcher import Dispatcher
from .tasks.store import TaskStore


def main() -> None:
    store = TaskStore(config.DB_PATH)
    hub = EventHub()
    dispatcher = Dispatcher(store, hub, nickname=config.NICKNAME)
    uvicorn.run(create_app(store, hub, dispatcher), host="127.0.0.1", port=config.PORT)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑全量测试** `cd /work/chatop/station && /tmp/claude-1000/station-venv/bin/python -m pytest -q` → 全绿
- [ ] **Step 5: 提交** `git commit -m "feat(station): FastAPI REST+SSE+静态挂载与 __main__ 入口"`

## Task 10: 前端骨架 + reducer/kpis（vitest）

**Files:** Create: `dashboard-web/package.json`, `dashboard-web/vite.config.ts`, `dashboard-web/tsconfig.json`, `dashboard-web/index.html`, `dashboard-web/src/main.tsx`, `dashboard-web/src/tokens.css`, `dashboard-web/src/streamReducer.ts`(+`.test.ts`), `dashboard-web/src/kpis.ts`(+`.test.ts`)

- [ ] **Step 1: 建包**

`dashboard-web/package.json`:
```json
{
  "name": "chatop-dashboard",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.5.4",
    "vite": "^5.4.0",
    "vitest": "^2.0.5"
  }
}
```

`dashboard-web/vite.config.ts`:
```ts
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  base: '/dashboard/',
  server: { proxy: { '/dashboard/api': 'http://127.0.0.1:8787' } },
})
```

`dashboard-web/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022", "lib": ["ES2022", "DOM"], "module": "ESNext",
    "moduleResolution": "bundler", "jsx": "react-jsx", "strict": true,
    "skipLibCheck": true, "noEmit": true, "types": ["vite/client"]
  },
  "include": ["src"]
}
```

`dashboard-web/index.html`:
```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Chatop 工位大屏</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.tsx"></script>
</body>
</html>
```

`dashboard-web/src/tokens.css`（深色指挥风，色板对齐 ChaCMD L0）:
```css
:root {
  --bg: #0a0f1e; --panel: #111827; --panel-2: #16203a; --line: #1f2a44;
  --text: #e5e7eb; --muted: #94a3b8; --accent: #22d3ee;
  --ok: #34d399; --warn: #fbbf24; --err: #f87171; --idle: #64748b;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
       font: 14px/1.5 -apple-system, "Noto Sans CJK SC", sans-serif; }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 12px; }
.muted { color: var(--muted); }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
.dot.ok { background: var(--ok); } .dot.err { background: var(--err); }
.dot.warn { background: var(--warn); } .dot.idle { background: var(--idle); }
button { background: var(--panel-2); color: var(--text); border: 1px solid var(--line);
         border-radius: 6px; padding: 4px 10px; cursor: pointer; }
button:hover { border-color: var(--accent); }
input, select, textarea { background: var(--panel-2); color: var(--text);
  border: 1px solid var(--line); border-radius: 6px; padding: 6px 8px; }
```

- [ ] **Step 2: 写 reducer/kpis 失败测试**

`dashboard-web/src/streamReducer.test.ts`:
```ts
import { describe, expect, it } from 'vitest'
import { applyEvent, initialStream, type StreamState } from './streamReducer'

const ev = (kind: string, jobId = 'j1', payload: Record<string, unknown> = {}) =>
  ({ job_id: jobId, kind, seq: 1, payload, ts: 1 })

describe('applyEvent', () => {
  it('progress 记录当前步与最近动作', () => {
    const s = applyEvent(initialStream(), ev('progress', 'j1', { text: 'editing' }))
    expect(s.jobs['j1'].state).toBe('running')
    expect(s.jobs['j1'].step).toBe('editing')
  })
  it('succeeded/failed 落终态', () => {
    let s: StreamState = applyEvent(initialStream(), ev('progress'))
    s = applyEvent(s, ev('succeeded'))
    expect(s.jobs['j1'].state).toBe('succeeded')
  })
  it('累计 tokens', () => {
    let s = applyEvent(initialStream(), ev('progress', 'j1', { tokens: 5 }))
    s = applyEvent(s, ev('succeeded', 'j1', { tokens: 7 }))
    expect(s.jobs['j1'].tokens).toBe(12)
  })
})
```

`dashboard-web/src/kpis.test.ts`:
```ts
import { describe, expect, it } from 'vitest'
import { computeKpis } from './kpis'

describe('computeKpis', () => {
  it('统计各态与成功率', () => {
    const k = computeKpis([
      { state: 'running' }, { state: 'succeeded' }, { state: 'succeeded' },
      { state: 'failed' }, { state: 'pending_approval' },
    ] as never)
    expect(k).toEqual({ total: 5, running: 1, waiting: 1, succeeded: 2, failed: 1, successRate: 2 / 3 })
  })
  it('无终态成功率为 0', () => {
    expect(computeKpis([]).successRate).toBe(0)
  })
})
```

- [ ] **Step 3: 装依赖跑测确认失败** `cd /work/chatop/dashboard-web && npm install && npx vitest run` → 失败
- [ ] **Step 4: 实现**

`dashboard-web/src/streamReducer.ts`:
```ts
export type StreamEvent = {
  job_id: string; kind: string; seq: number
  payload: Record<string, unknown>; ts: number
}
export type JobLive = { state: string; step: string; tokens: number; lastTs: number }
export type StreamState = { jobs: Record<string, JobLive> }

export const initialStream = (): StreamState => ({ jobs: {} })

export function applyEvent(s: StreamState, ev: StreamEvent): StreamState {
  const prev = s.jobs[ev.job_id] ?? { state: 'running', step: '', tokens: 0, lastTs: 0 }
  const terminal = ev.kind === 'succeeded' || ev.kind === 'failed'
  const next: JobLive = {
    state: terminal ? ev.kind : prev.state,
    step: typeof ev.payload.text === 'string' && ev.payload.text ? ev.payload.text : prev.step,
    tokens: prev.tokens + (typeof ev.payload.tokens === 'number' ? ev.payload.tokens : 0),
    lastTs: ev.ts,
  }
  return { jobs: { ...s.jobs, [ev.job_id]: next } }
}
```

`dashboard-web/src/kpis.ts`:
```ts
export type TaskLike = { state: string }
export type Kpis = {
  total: number; running: number; waiting: number
  succeeded: number; failed: number; successRate: number
}

export function computeKpis(tasks: TaskLike[]): Kpis {
  const by = (st: string) => tasks.filter(t => t.state === st).length
  const succeeded = by('succeeded'); const failed = by('failed')
  const done = succeeded + failed
  return {
    total: tasks.length, running: by('running'), waiting: by('pending_approval'),
    succeeded, failed, successRate: done ? succeeded / done : 0,
  }
}
```

`dashboard-web/src/main.tsx`:
```tsx
import { createRoot } from 'react-dom/client'
import App from './App'
import './tokens.css'

createRoot(document.getElementById('root')!).render(<App />)
```

（`App.tsx` 在 Task 11 实现；本步先放最小占位以便 build 通过：）
```tsx
export default function App() {
  return <div className="panel">chatop 工位大屏 loading…</div>
}
```

- [ ] **Step 5: 跑测通过 + build 通过** `npx vitest run && npm run build`
- [ ] **Step 6: 提交** `git add dashboard-web/ && git commit -m "feat(dashboard-web): Vite+React 骨架+streamReducer/kpis（vitest 绿）"`（`node_modules`/`dist` 不入库：仓库根 `.gitignore` 若未覆盖则本任务顺带加 `dashboard-web/node_modules` `dashboard-web/dist` 两行）

## Task 11: 六区组件 + SSE hook + embed

**Files:** Create: `dashboard-web/src/api.ts`, `dashboard-web/src/components/{TopBar,AgentWall,TaskList,DispatchBox,SystemPanel}.tsx`；Modify: `dashboard-web/src/App.tsx`

- [ ] **Step 1: api.ts（轮询 + SSE hook）**

```ts
import { useEffect, useRef, useState } from 'react'
import { applyEvent, initialStream, type StreamState } from './streamReducer'

const BASE = '/dashboard/api'

export function usePoll<T>(path: string, intervalMs: number, fallback: T): T {
  const [data, setData] = useState<T>(fallback)
  useEffect(() => {
    let alive = true
    const tick = () =>
      fetch(BASE + path).then(r => r.json()).then(d => { if (alive) setData(d) }).catch(() => {})
    tick()
    const t = setInterval(tick, intervalMs)
    return () => { alive = false; clearInterval(t) }
  }, [path, intervalMs])
  return data
}

export function useEventStream(): { stream: StreamState; connected: boolean } {
  const [stream, setStream] = useState<StreamState>(initialStream())
  const [connected, setConnected] = useState(false)
  const retryRef = useRef(1000)
  useEffect(() => {
    let es: EventSource | null = null
    let stop = false
    const connect = () => {
      if (stop) return
      es = new EventSource(BASE + '/events')
      es.onopen = () => { setConnected(true); retryRef.current = 1000 }
      es.onmessage = e => { try { setStream(s => applyEvent(s, JSON.parse(e.data))) } catch { /* skip */ } }
      es.onerror = () => {
        setConnected(false); es?.close()
        setTimeout(connect, Math.min((retryRef.current *= 2), 30000))
      }
    }
    connect()
    return () => { stop = true; es?.close() }
  }, [])
  return { stream, connected }
}

export const dispatchTask = (agent: string, goal: string, workdir?: string) =>
  fetch(BASE + '/dispatch', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent, goal, workdir: workdir || null }),
  }).then(r => { if (!r.ok) throw new Error(String(r.status)); return r.json() })
```

- [ ] **Step 2: 组件（每个一个文件，代码如下）**

`components/TopBar.tsx`:
```tsx
import { computeKpis, type TaskLike } from '../kpis'

const EMBED = new URLSearchParams(location.search).get('embed') === '1'

export default function TopBar({ tasks, agents, sys, connected }: {
  tasks: TaskLike[]; agents: { installed?: boolean; running?: boolean }[]
  sys: { cpu?: number; mem?: number; disk?: number }; connected: boolean
}) {
  const k = computeKpis(tasks)
  const installed = agents.filter(a => a.installed).length
  const running = agents.filter(a => a.running).length
  return (
    <header className="panel" style={{ display: 'flex', gap: 18, alignItems: 'center', flexWrap: 'wrap' }}>
      {!EMBED && <strong style={{ color: 'var(--accent)' }}>🖥️ 工位大屏</strong>}
      <span><span className={`dot ${connected ? 'ok' : 'err'}`} />{connected ? '事件流已连' : '事件流断开'}</span>
      <span className="muted">独立模式</span>
      <span>智能体 {installed} 装 / {running} 跑</span>
      <span>任务 {k.total} · 运行 {k.running} · 待批 {k.waiting} · 成功率 {(k.successRate * 100).toFixed(0)}%</span>
      <span className="muted">CPU {sys.cpu ?? '–'}% · MEM {sys.mem ?? '–'}% · DISK {sys.disk ?? '–'}%</span>
      {!EMBED && <span className="muted" style={{ marginLeft: 'auto' }}>{new Date().toLocaleTimeString()}</span>}
    </header>
  )
}
```

`components/AgentWall.tsx`:
```tsx
export type Agent = {
  id: string; name: string; installed: boolean; agent_type?: string
  configured?: boolean; model?: string; running?: boolean
  active_sessions?: number; cpu?: number; mem_mb?: number; dispatchable?: boolean
}

const statusDot = (a: Agent) =>
  !a.installed ? 'idle' : a.running || (a.active_sessions ?? 0) > 0 ? 'ok' : a.configured ? 'idle' : 'warn'

export default function AgentWall({ agents, onPick }: { agents: Agent[]; onPick: (id: string) => void }) {
  const installed = agents.filter(a => a.installed)
  if (!installed.length)
    return <div className="panel muted">尚未安装智能体——打开「应用管理」安装第一个 →</div>
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(210px,1fr))', gap: 10 }}>
      {installed.map(a => (
        <div key={a.id} className="panel">
          <div><span className={`dot ${statusDot(a)}`} /><strong>{a.name}</strong>
            <span className="muted"> {a.agent_type === 'runtime' ? '常驻' : '会话式'}</span></div>
          <div className="muted">{a.configured ? `模型: ${a.model || '已配置'}` : '⚠ 未配置'}</div>
          <div className="muted">
            {a.running ? `运行中 CPU ${a.cpu}% MEM ${a.mem_mb}M` : `活动会话 ${a.active_sessions ?? 0}`}
          </div>
          {a.dispatchable && <button onClick={() => onPick(a.id)}>派活给它</button>}
        </div>
      ))}
    </div>
  )
}
```

`components/TaskList.tsx`:
```tsx
import type { StreamState } from '../streamReducer'

export type Task = {
  id: string; agent: string; goal: string; state: string
  current_step: string; tokens: number; source: string; created_at: number
}
const ICON: Record<string, string> = {
  running: '▶', succeeded: '✓', failed: '✗', pending_approval: '⏸', queued: '…', cancelled: '⊘',
}

export default function TaskList({ tasks, live }: { tasks: Task[]; live: StreamState }) {
  if (!tasks.length) return <div className="panel muted">暂无任务——左侧派一个试试</div>
  return (
    <div className="panel" style={{ overflowY: 'auto', maxHeight: '60vh' }}>
      {tasks.map(t => {
        const l = live.jobs[t.id]
        const state = l?.state && t.state === 'running' ? l.state : t.state
        const step = l?.step || t.current_step
        return (
          <div key={t.id} style={{ borderBottom: '1px solid var(--line)', padding: '6px 0' }}>
            <div>{ICON[state] ?? '·'} <strong>{t.goal.slice(0, 60)}</strong>
              <span className="muted"> @{t.agent} · {state}{t.source === 'detected' ? ' · 侦测' : ''}</span></div>
            {step && <div className="muted" style={{ paddingLeft: 18 }}>└ {step.slice(0, 80)}</div>}
          </div>
        )
      })}
    </div>
  )
}
```

`components/DispatchBox.tsx`:
```tsx
import { useState } from 'react'
import { dispatchTask } from '../api'
import type { Agent } from './AgentWall'

export default function DispatchBox({ agents, picked }: { agents: Agent[]; picked: string }) {
  const targets = agents.filter(a => a.installed && a.dispatchable)
  const [agent, setAgent] = useState('')
  const [goal, setGoal] = useState('')
  const [note, setNote] = useState('')
  const chosen = agent || picked || targets[0]?.id || ''
  const send = () => {
    if (!chosen || !goal.trim()) return
    dispatchTask(chosen, goal.trim())
      .then(r => { setNote(`已派活 #${r.job_id}`); setGoal('') })
      .catch(e => setNote(`派活失败: ${e.message}`))
  }
  return (
    <div className="panel" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
      <select value={chosen} onChange={e => setAgent(e.target.value)}>
        {targets.map(a => <option key={a.id} value={a.id}>@{a.name}</option>)}
      </select>
      <input style={{ flex: 1 }} placeholder="要做什么…" value={goal}
             onChange={e => setGoal(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()} />
      <button onClick={send} disabled={!chosen}>派活</button>
      {note && <span className="muted">{note}</span>}
    </div>
  )
}
```

`components/SystemPanel.tsx`:
```tsx
export type Sys = {
  cpu?: number; mem?: number; disk?: number; uptime?: number
  services?: { name: string; ok: boolean }[]; ports?: number[]; vnc_online?: boolean
}

export default function SystemPanel({ sys }: { sys: Sys }) {
  return (
    <div className="panel">
      <div><strong>容器运行状态</strong>
        <span className="muted"> 运行 {Math.floor((sys.uptime ?? 0) / 3600)}h</span></div>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 6 }}>
        {(sys.services ?? []).map(s => (
          <span key={s.name}><span className={`dot ${s.ok ? 'ok' : 'err'}`} />{s.name}</span>
        ))}
        <span><span className={`dot ${sys.vnc_online ? 'ok' : 'idle'}`} />VNC 会话</span>
      </div>
      <div className="muted" style={{ marginTop: 6 }}>监听端口: {(sys.ports ?? []).join(', ') || '–'}</div>
    </div>
  )
}
```

- [ ] **Step 3: App.tsx 组装**

```tsx
import { useState } from 'react'
import { useEventStream, usePoll } from './api'
import AgentWall, { type Agent } from './components/AgentWall'
import DispatchBox from './components/DispatchBox'
import SystemPanel, { type Sys } from './components/SystemPanel'
import TaskList, { type Task } from './components/TaskList'
import TopBar from './components/TopBar'

export default function App() {
  const agents = usePoll<Agent[]>('/agents', 10000, [])
  const tasks = usePoll<Task[]>('/tasks', 5000, [])
  const sys = usePoll<Sys>('/system', 5000, {})
  const { stream, connected } = useEventStream()
  const [picked, setPicked] = useState('')
  return (
    <div style={{ display: 'grid', gap: 10, padding: 10,
                  gridTemplateRows: 'auto 1fr auto auto', minHeight: '100vh' }}>
      <TopBar tasks={tasks} agents={agents} sys={sys} connected={connected} />
      <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr', gap: 10 }}>
        <AgentWall agents={agents} onPick={setPicked} />
        <TaskList tasks={tasks} live={stream} />
      </div>
      <DispatchBox agents={agents} picked={picked} />
      <SystemPanel sys={sys} />
    </div>
  )
}
```

- [ ] **Step 4: 验证** `cd /work/chatop/dashboard-web && npx vitest run && npm run build` → 全绿
- [ ] **Step 5: 提交** `git commit -m "feat(dashboard-web): 六区大屏组件+SSE hook+embed 参数"`

## Task 12: 镜像接线（Dockerfile + Caddy + 自启 + VERSION）

**Files:** Create: `station/start-station.sh`；Modify: `Dockerfile`, `caddy/Caddyfile`, `app-manager/chatop-seed-home.sh`, `VERSION`

- [ ] **Step 1: start-station.sh**

```bash
#!/usr/bin/env bash
set -e
export STATION_PORT="${STATION_PORT:-8787}"
export APPS_CATALOG="${APPS_CATALOG:-/etc/chatop/apps-catalog.json}"
cd /opt/station
exec /opt/station-venv/bin/python -m station
```

- [ ] **Step 2: Dockerfile 增量**（在现有 `FROM node:20-alpine AS web` 之后加第二个前端 stage；在 app 层加 station）

```dockerfile
# === dashboard-web 构建 ===
FROM node:20-alpine AS dashweb
WORKDIR /src
COPY dashboard-web/ ./
RUN --mount=type=cache,target=/root/.npm npm install && npm run build
```

app 层（紧邻 app-manager COPY 块后）：
```dockerfile
# === station：工位本地大屏常驻服务 ===
COPY station/station/ /opt/station/station/
COPY station/start-station.sh /usr/local/bin/start-station.sh
COPY --from=dashweb /src/dist/ /opt/station/station/web/
RUN python3.11 -m venv /opt/station-venv && \
    /opt/station-venv/bin/pip install --no-cache-dir \
      'fastapi>=0.110,<1' 'uvicorn>=0.30,<1' 'psutil>=5.9' && \
    chmod +x /usr/local/bin/start-station.sh && \
    mkdir -p /opt/chatop-seed-home/.config/autostart && \
    printf '[Desktop Entry]\nType=Application\nName=Chatop Dashboard\nExec=/usr/local/bin/start-dashboard-window.sh\nIcon=utilities-system-monitor\nX-GNOME-Autostart-enabled=true\n' \
      > /opt/chatop-seed-home/.config/autostart/chatop-dashboard.desktop && \
    printf '#!/bin/bash\nfor i in $(seq 1 60); do curl -fsS http://127.0.0.1:8787/dashboard/api/system >/dev/null 2>&1 && break; sleep 1; done\nexec /usr/bin/google-chrome-stable --app=http://127.0.0.1:8787/dashboard --start-fullscreen --no-first-run\n' \
      > /usr/local/bin/start-dashboard-window.sh && \
    chmod +x /usr/local/bin/start-dashboard-window.sh
```

custom_startup printf（第 57 行）在 `set-wallpaper.sh` 行后**插入**（保持末尾 `wait` 不动）：
```
/usr/local/bin/start-station.sh >/tmp/station.log 2>&1 &\n
```

- [ ] **Step 3: Caddyfile 加路由**（放在 `handle /files*` 块之后）

```caddyfile
    # 工位本地大屏（station）：登录后可访问，SSE 长连接直通
    handle /dashboard* {
        forward_auth 127.0.0.1:8686 {
            uri /auth
        }
        reverse_proxy 127.0.0.1:8787 {
            flush_interval -1
        }
    }
```

- [ ] **Step 4: seed WANT 哨兵 +1**：`app-manager/chatop-seed-home.sh` 中 `WANT=1` 改 `WANT=2`（否则老卷不播 autostart 文件）。
- [ ] **Step 5: VERSION +1**（读当前值 +1 写回）。
- [ ] **Step 6: 语法冒烟**：`bash -n station/start-station.sh && bash -n app-manager/chatop-seed-home.sh`；有 docker 环境则 `docker build -t chatop:dev .`（无则标注留真机）。
- [ ] **Step 7: 提交** `git commit -m "feat(chatop): station 进镜像+Caddy /dashboard 路由+桌面自启大屏窗口"`

## Task 13: 真机验收清单（需用户机器，逐条打勾后收尾）

- [ ] `./build-and-run.sh` 构建并起容器，`docker logs` 无 station 报错，`/tmp/station.log` 正常。
- [ ] 外部浏览器 `https://<host>:7443/dashboard` → 跳登录 → 登录后见大屏；顶栏 KPI/系统区有数。
- [ ] 进 VNC 桌面：自启全屏大屏窗口出现（chrome --app）。
- [ ] A 区见已装智能体卡（claude-code/codex/openclaw），配置状态与实际一致。
- [ ] C 区 @claude-code 派一个真任务 → B 区实时流式 → 终态正确 → SQLite 有记录。
- [ ] 杀掉 openclaw 进程 → 10s 内卡片状态灯变化；`kill` station → 桌面窗口显示断连，VNC/files 不受影响。
- [ ] 全部通过后 `sudo git push origin main`。

---

## Self-Review 备忘

- spec §2 六区 vs 任务：顶栏(T10/11)、A(T4/5/11)、B(T2/8/11)、C(T7/11)、D(T6/11)、E=v1.5 不在本计划 ✅
- 双入口：外部(T12 Caddy)、桌面自启(T12 desktop 文件) ✅；embed 参数(T11 TopBar EMBED) ✅（ticket 桩=v2，spec 已注明）
- 类型一致性：事件 dict 字段（job_id/kind/seq/payload/ts）在 adapter/store/hub/前端 StreamEvent 一致；状态集 store._ALLOWED 与前端 ICON/kpis 对齐 ✅
- 红线：key 明文不读取内容只查存在性+model 字段；station 只听 127.0.0.1 ✅
