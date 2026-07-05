# ChaCMD 后端迁仓 + 浏览器向 SSE 事件流 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把已实现的 ChaCMD 后端（97 tests）从 `/work/chatop/chacmd` 迁到 `/work/chayuan-desktop/chacmd`（对齐 §3.6 双 SKU 落点），并新增一个浏览器向 SSE 事件流端点（指挥大屏 v1 的数据源前置）。

**Architecture:** 迁仓是纯搬运 + 重建测试基线（代码本按 `ChayuanClient` 全 HTTP 抽象写，无需改逻辑）。SSE 通过新增一个进程内 `EventStreamHub`（扇出广播）实现：`EventIngest` 每处理一个事件就 broadcast 到 hub，FastAPI 的 `GET /api/v1/stream` 用 `StreamingResponse` 把 hub 事件按 W3C EventSource 格式（`data: <json>\n\n`）推给浏览器。不依赖 NATS 通配符，InMemoryEventBus 语义不变。

**Tech Stack:** Python 3.11 / FastAPI StreamingResponse / asyncio.Queue 扇出 / pytest-asyncio。

**工作目录:** 迁移后 `/work/chayuan-desktop/chacmd/`（git 仓 chayuan-desktop-own，分支 main，**工作树有 2780 处非本任务的既有改动——只路径限定 `git add chacmd/`，绝不 `git add -A`，绝不碰那 2780 处**）。

**测试环境:** `<VENV>` = `/tmp/claude-1000/-work-chatop/1a6d2d07-e5ea-4b26-a419-42ea7d589603/scratchpad/cvenv/bin`（py3.11，装了 fastapi/sqlalchemy/httpx/pytest-asyncio auto/asyncpg/ruff）。迁移后需 `<VENV>/pip install -e /work/chayuan-desktop/chacmd` 重指编辑安装。基线 97 passed。

---

## File Structure

### 迁移（Task 0，整体搬运）
`/work/chatop/chacmd/` 整棵（`chacmd/` 包 + `tests/` + `docs/` + `pyproject.toml` + `ruff.toml`）→ `/work/chayuan-desktop/chacmd/`。

### 新增文件（SSE，在迁移后的 chayuan-desktop/chacmd 内）
- `chacmd/api/stream.py` — `EventStreamHub`（扇出广播 + SSE 格式化）
- `tests/test_stream_hub.py` — hub 单测
- `tests/test_sse_endpoint.py` — SSE 端点集成测

### 修改文件
- `chacmd/orchestrator/ingest.py` — `EventIngest` 加可选 `stream_hub`，handle 时 broadcast
- `chacmd/api/app.py` — `create_app` 加可选 `stream_hub`，挂 `GET /api/v1/stream`
- `chacmd/container.py` — 建 hub，注入 EventIngest 与 create_app 用同一实例
- `chacmd/cli.py` — create_app 传 hub

---

## Task 0: 迁仓 chatop/chacmd → chayuan-desktop/chacmd

**Files:**
- Move: `/work/chatop/chacmd/**` → `/work/chayuan-desktop/chacmd/**`

- [ ] **Step 1: 复制整棵包（排除缓存）到目标**

Run:
```bash
mkdir -p /work/chayuan-desktop/chacmd
rsync -a --exclude='__pycache__' --exclude='.pytest_cache' --exclude='.ruff_cache' --exclude='*.egg-info' \
  /work/chatop/chacmd/ /work/chayuan-desktop/chacmd/
ls /work/chayuan-desktop/chacmd/   # 期望: chacmd docs pyproject.toml ruff.toml tests
```

- [ ] **Step 2: 重指编辑安装到新位置并跑测试**

Run:
```bash
VENV=/tmp/claude-1000/-work-chatop/1a6d2d07-e5ea-4b26-a419-42ea7d589603/scratchpad/cvenv/bin
$VENV/pip install -e /work/chayuan-desktop/chacmd -q
cd /work/chayuan-desktop/chacmd && $VENV/python -m pytest -q 2>&1 | tail -3
```
Expected: `97 passed`

- [ ] **Step 3: 提交到 chayuan-desktop（仅路径限定）**

Run:
```bash
cd /work/chayuan-desktop
git add chacmd/
git status --short chacmd/ | head -3   # 确认只 add 了 chacmd/ 下文件
git commit -q -m "feat(chacmd): 迁入后端 Orchestrator(P0 全量, 97 tests) 至母体 monorepo(§3.6 双 SKU)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
git log --oneline -1 | cat
```

> 从 chatop 删除 chacmd 放到最后（Task 5），确认新仓一切就绪后再删，避免中途丢失。

---

## Task 1: EventStreamHub（扇出广播 + SSE 格式化）

**Files:**
- Create: `chacmd/api/stream.py`
- Test: `tests/test_stream_hub.py`

- [ ] **Step 1: 写失败测试**

`tests/test_stream_hub.py`:
```python
import asyncio

import pytest

from chacmd.api.stream import EventStreamHub, sse_format


def test_sse_format_is_eventsource_frame():
    assert sse_format({"kind": "started", "seq": 0}) == 'data: {"kind": "started", "seq": 0}\n\n'


@pytest.mark.asyncio
async def test_broadcast_fans_out_to_all_subscribers():
    hub = EventStreamHub()
    a = hub.register()
    b = hub.register()
    await hub.broadcast({"kind": "x"})
    assert await asyncio.wait_for(a.get(), 1) == {"kind": "x"}
    assert await asyncio.wait_for(b.get(), 1) == {"kind": "x"}
    hub.unregister(a)
    hub.unregister(b)


@pytest.mark.asyncio
async def test_unregister_stops_delivery():
    hub = EventStreamHub()
    q = hub.register()
    hub.unregister(q)
    await hub.broadcast({"kind": "y"})   # 无订阅者，不应抛
    assert q.empty()


@pytest.mark.asyncio
async def test_full_subscriber_queue_drops_not_blocks():
    # 慢消费者队列满时丢弃最旧，不阻塞广播（背压保护）
    hub = EventStreamHub(maxsize=1)
    q = hub.register()
    await hub.broadcast({"n": 1})
    await hub.broadcast({"n": 2})   # 队列满，丢最旧，不阻塞
    assert await asyncio.wait_for(q.get(), 1) == {"n": 2}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `<VENV>/python -m pytest tests/test_stream_hub.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 EventStreamHub**

`chacmd/api/stream.py`:
```python
from __future__ import annotations

import asyncio
import json


def sse_format(event: dict) -> str:
    """W3C EventSource 帧：data: <json>\\n\\n（浏览器 EventSource / net.sse 消费）。"""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


class EventStreamHub:
    """进程内扇出广播：每个浏览器 SSE 连接注册一个队列，broadcast 推给所有队列。

    队列满时丢最旧（背压保护，慢消费者不拖垮广播）。
    """

    def __init__(self, maxsize: int = 1000) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._maxsize = maxsize

    def register(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._maxsize)
        self._subscribers.add(q)
        return q

    def unregister(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)

    async def broadcast(self, event: dict) -> None:
        for q in list(self._subscribers):
            if q.full():
                try:
                    q.get_nowait()  # 丢最旧
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(event)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `<VENV>/python -m pytest tests/test_stream_hub.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd /work/chayuan-desktop
git add chacmd/chacmd/api/stream.py chacmd/tests/test_stream_hub.py
git commit -q -m "feat(chacmd): EventStreamHub 扇出广播 + SSE 帧格式化(背压丢最旧)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: EventIngest 广播到 hub

**Files:**
- Modify: `chacmd/orchestrator/ingest.py`
- Test: `tests/test_ingest.py`（追加）

- [ ] **Step 1: 写失败测试**

`tests/test_ingest.py` 追加（沿用文件现有 import；若无则加 `from chacmd.api.stream import EventStreamHub`、`from chacmd.domain.events import Event`）：
```python
@pytest.mark.asyncio
async def test_ingest_broadcasts_each_event_to_stream_hub(db):
    from chacmd.api.stream import EventStreamHub
    from chacmd.domain.events import Event
    from chacmd.domain.repository import AuditRepository, JobRepository
    from chacmd.interfaces.eventbus import InMemoryEventBus
    from chacmd.orchestrator.ingest import EventIngest

    jobs = JobRepository(db)
    job = await jobs.create(code="c", goal="g", dept="d1")
    hub = EventStreamHub()
    q = hub.register()
    ingest = EventIngest(InMemoryEventBus(), jobs, AuditRepository(db), stream_hub=hub)
    await ingest.handle(Event(job.id, job.id, "dev", "started", 0, {}))
    got = await asyncio.wait_for(q.get(), 1)
    assert got["kind"] == "started"
    assert got["job_id"] == job.id
    assert "traceparent" in got  # 复用已注入的 traceparent
```
（确保文件顶部有 `import asyncio` 和 `db` fixture；`db` fixture 见 test_dispatcher.py 风格：内存 sqlite。若本文件无 db fixture，加：）
```python
@pytest.fixture
async def db():
    from chacmd.interfaces.db import Database
    d = Database(url="sqlite+aiosqlite:///:memory:")
    await d.create_all()
    yield d
    await d.dispose()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `<VENV>/python -m pytest tests/test_ingest.py -q -k broadcast`
Expected: FAIL（EventIngest 无 stream_hub 参数）

- [ ] **Step 3: 改 EventIngest**

`chacmd/orchestrator/ingest.py` 的 `__init__` 与 `handle`：
```python
    def __init__(
        self, bus: EventBus, jobs: JobRepository, audit: AuditRepository, stream_hub: object | None = None
    ) -> None:
        self._bus = bus
        self._jobs = jobs
        self._audit = audit
        self._stream_hub = stream_hub
```
在 `handle` 里构造出 `msg`（已注入 traceparent）后、publish 之后，追加广播（带 job_id/container 便于大屏过滤）：
```python
        msg = inject_traceparent(
            {"kind": e.kind, "seq": e.seq, "payload": e.payload,
             "job_id": e.job_id, "container": e.container}, job_id=e.job_id
        )
        await self._bus.publish(e.subject(), msg)
        if self._stream_hub is not None:
            await self._stream_hub.broadcast(msg)
```
（注意：原 msg 未含 job_id/container，此处补上——大屏按员工/任务过滤需要；不破坏既有订阅者，只是多两个键。）

- [ ] **Step 4: 跑测试确认通过 + 回归**

Run:
```bash
<VENV>/python -m pytest tests/test_ingest.py tests/test_e2e_m4.py -q
```
Expected: PASS（test_e2e_m4 里 traceparent 断言仍过，因 msg 仍含 traceparent/baggage）

- [ ] **Step 5: 提交**

```bash
cd /work/chayuan-desktop
git add chacmd/chacmd/orchestrator/ingest.py chacmd/tests/test_ingest.py
git commit -q -m "feat(chacmd): EventIngest 广播事件到 StreamHub(带 job_id/container 供大屏过滤)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: GET /api/v1/stream SSE 端点

**Files:**
- Modify: `chacmd/api/app.py`
- Test: `tests/test_sse_endpoint.py`

- [ ] **Step 1: 写失败测试**

`tests/test_sse_endpoint.py`:
```python
import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from chacmd.api.app import create_app
from chacmd.api.stream import EventStreamHub
from chacmd.interfaces.db import Database


@pytest.mark.asyncio
async def test_stream_endpoint_emits_sse_frames():
    db = Database(url="sqlite+aiosqlite:///:memory:")
    await db.create_all()
    hub = EventStreamHub()
    app = create_app(db, stream_hub=hub)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        async with c.stream("GET", "/api/v1/stream") as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            await hub.broadcast({"kind": "started", "job_id": "j1"})
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    assert '"kind": "started"' in line
                    break
    await db.dispose()


@pytest.mark.asyncio
async def test_stream_absent_when_hub_not_injected():
    db = Database(url="sqlite+aiosqlite:///:memory:")
    await db.create_all()
    app = create_app(db)  # 无 hub
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/v1/stream")
    assert r.status_code == 404
    await db.dispose()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `<VENV>/python -m pytest tests/test_sse_endpoint.py -q`
Expected: FAIL（端点不存在）

- [ ] **Step 3: 挂 SSE 端点**

`chacmd/api/app.py`：`create_app` 签名加 `stream_hub`：
```python
def create_app(db: Database, chayuan: object | None = None, stream_hub: object | None = None) -> FastAPI:
```
在 `return app` 之前追加（放在 chayuan shim 块附近）：
```python
    if stream_hub is not None:
        from fastapi.responses import StreamingResponse

        from chacmd.api.stream import sse_format

        @app.get("/api/v1/stream")
        async def event_stream():
            # 大屏 v1 数据源：把 EventStreamHub 事件按 EventSource 帧推给浏览器
            q = stream_hub.register()

            async def gen():
                try:
                    while True:
                        event = await q.get()
                        yield sse_format(event)
                finally:
                    stream_hub.unregister(q)

            return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `<VENV>/python -m pytest tests/test_sse_endpoint.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd /work/chayuan-desktop
git add chacmd/chacmd/api/app.py chacmd/tests/test_sse_endpoint.py
git commit -q -m "feat(chacmd): GET /api/v1/stream 浏览器向 SSE 事件流(大屏 v1 数据源)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: 组合根接线 + 端到端 SSE

**Files:**
- Modify: `chacmd/container.py`, `chacmd/cli.py`
- Test: `tests/test_e2e_m4.py`（追加）

- [ ] **Step 1: 写失败测试（派活→SSE 收到事件）**

`tests/test_e2e_m4.py` 追加：
```python
@pytest.mark.asyncio
async def test_dispatch_events_reach_sse_hub(tmp_path):
    c = await build_container(_settings(tmp_path), use_fakes=True)
    assert c.stream_hub is not None
    q = c.stream_hub.register()
    await c.containers.upsert(nickname="dev", session="s1", dept="d1")
    job = await c.jobs.create(code="c", goal="g", dept="d1")
    await c.dispatcher.dispatch(job_id=job.id, nickname="dev", subject="u1", system_prompt="p")
    kinds = []
    while not q.empty():
        kinds.append((await q.get())["kind"])
    assert "started" in kinds and "succeeded" in kinds
    await c.db.dispose()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `<VENV>/python -m pytest tests/test_e2e_m4.py -q -k sse_hub`
Expected: FAIL（Container 无 stream_hub 字段）

- [ ] **Step 3: 组合根建 hub 并注入**

`chacmd/container.py`：
- `Container` dataclass 加字段 `stream_hub: object`（放 workspace 前）。
- `build_container` 里建 hub 并传给 EventIngest：
```python
    from chacmd.api.stream import EventStreamHub
    stream_hub = EventStreamHub()
    ingest = EventIngest(bus, jobs, audit, stream_hub=stream_hub)
```
- `Container(...)` 构造追加 `stream_hub=stream_hub,`。

`chacmd/cli.py`：`create_app(container.db, chayuan=container.chayuan)` 改为：
```python
        app = create_app(container.db, chayuan=container.chayuan, stream_hub=container.stream_hub)
```

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run:
```bash
cd /work/chayuan-desktop/chacmd
<VENV>/python -m pytest -q 2>&1 | tail -3
<VENV>/ruff check chacmd/ 2>&1 | tail -1
```
Expected: 全绿（约 106 passed）、ruff All checks passed

- [ ] **Step 5: 提交**

```bash
cd /work/chayuan-desktop
git add chacmd/chacmd/container.py chacmd/chacmd/cli.py chacmd/tests/test_e2e_m4.py
git commit -q -m "feat(chacmd): 组合根接 StreamHub + 端到端派活事件达 SSE

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: 从 chatop 删除已迁走的 chacmd

**Files:**
- Delete: `/work/chatop/chacmd/`

- [ ] **Step 1: 确认新仓测试全绿（迁移已完成、可安全删源）**

Run:
```bash
cd /work/chayuan-desktop/chacmd && <VENV>/python -m pytest -q 2>&1 | tail -2
```
Expected: 全绿。若不绿，**停止**，不要删 chatop 源。

- [ ] **Step 2: 从 chatop 删除并提交**

```bash
cd /work/chatop
git rm -r -q chacmd/
git commit -q -m "chore(chacmd): 后端已迁至 chayuan-desktop/chacmd(§3.6 双 SKU), 从 chatop 移除

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
git log --oneline -1 | cat
```

- [ ] **Step 3: 更新记忆指针**

编辑 `/home/admin/.claude/projects/-work-chatop/memory/chacmd-backend-progress.md`：把"落点 `/work/chatop/chacmd/`"改为"落点 `/work/chayuan-desktop/chacmd/`（2026-07-05 迁自 chatop）"，并注明新增 `GET /api/v1/stream` SSE。

---

## Self-Review

**Spec 覆盖（对照总纲 §5 v1 前置 #3 + D1）：**
- D1 后端迁仓 chayuan-desktop/chacmd → Task 0 + Task 5 ✓
- v1 前置 #3 浏览器向 SSE 事件流 → Task 1–4 ✓（hub 广播 + 端点 + 组合根接线 + 端到端）

**Placeholder 扫描：** 无 TODO/后补；每步含实际代码与命令。

**类型一致性：** `EventStreamHub.register()→asyncio.Queue`（Task1）↔ ingest/endpoint/container 用法一致；`sse_format(dict)→str`（Task1）↔ 端点用法一致；`create_app(db, chayuan, stream_hub)`（Task3）↔ cli 调用（Task4）一致，且对旧 `create_app(db)`/`create_app(db, chayuan=...)` 向后兼容（新参默认 None）；`EventIngest(..., stream_hub=None)`（Task2）↔ container 注入（Task4）一致。

**不在本计划（下一个计划）：** 察元 3 注入 seam + apps/chacmd Tauri 壳 + packages/chacmd-features + 3D 星群大屏（前端子系统，需 pnpm/Tauri 工具链、动母体基座，单独成计划）。

---

## Execution Handoff

计划保存于 `docs/superpowers/plans/2026-07-05-chacmd-backend-relocate-and-sse.md`（chatop 仓）。
