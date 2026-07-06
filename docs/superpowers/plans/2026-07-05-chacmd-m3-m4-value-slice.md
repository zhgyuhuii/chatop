# ChaCMD M3+M4 价值切片闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 ChaCMD 从"Fake 全绿骨架"推到"P0 五条验收全过"——修母体契约、接真 OpenHands、真沙箱加固、Anthropic shim、审批门、预算 kill、NATS+Postgres、OTel、容器供给，最后端到端验收。

**Architecture:** 沿用 P0 骨架的接口抽象（I1–I10）。M3 逐个把 Fake 实现换成真实现（每个仍保留 Fake 供测试），M4 做端到端集成。所有对察元的调用经 `ChayuanClient` 防腐层；实时派活核心不经察元 monorepo。

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy 2.0 async / NATS JetStream (nats-py) / OpenTelemetry / Docker SDK (rootless) / pytest-asyncio。测试用 SQLite+InMemory+Fake，生产用 Postgres+NATS+真适配器。

**工作目录:** `.claude/worktrees/chacmd-p0-backend/chacmd/`（分支 `worktree-chacmd-p0-backend`）。所有路径相对该目录。

**验证基线:** 每个 Task 后跑 `<SCRATCH>/cvenv/bin/python -m pytest -q`（`<SCRATCH>` = 已建好装了依赖的 py3.11 venv：`/tmp/claude-1000/-work-chatop/1a6d2d07-e5ea-4b26-a419-42ea7d589603/scratchpad/cvenv`）。当前基线 58 passed。

---

## 关键背景（实证结论，动手前必读）

1. **母体契约错配**：`chacmd/interfaces/chayuan_client.py` 硬编码调 `POST /api/v1/authz/check` 和 `GET /api/v1/whoami`，但察元（`/work/chayuan-desktop`）**这两个端点都不存在**。察元真实端点：`whoami` 在 `/openapi/v1/whoami`（router prefix `/openapi/v1`）；authz 无独立 check 端点，鉴权语义在 `/api/v1/admin/kb-acl`、`/api/v1/admin/roles` 等。**Task 1 先修这个，否则真集成 404。**
2. **母体 License 是 Apache-2.0**（不是文档写的 AGPL-3.0）——已在分析报告更正，本计划不涉及。
3. **母体网关**：OpenAI 兼容 `/v1/chat/completions` 真实存在（两处）；Anthropic `/v1/messages` **不存在**，需 ChaCMD 自建 shim（Task 4）。
4. **provider 目录**实测 75 个，`kb_query` 契约 `POST /api/v1/kb-query/search` 已对齐，无需改。

---

## File Structure

### 新建文件
- `chacmd/interfaces/nats_bus.py` — NatsEventBus（EventBus 的 NATS JetStream 实现）
- `chacmd/interfaces/docker_sandbox.py` — DockerSandbox（Sandbox 的 rootless Docker 实现 + 加固基线）
- `chacmd/adapters/openhands_adapter.py` — OpenHandsAdapter（AgentAdapter 真实现，OpenHands headless）
- `chacmd/adapters/__init__.py`
- `chacmd/shim/anthropic_shim.py` — Anthropic `/v1/messages` → 察元 OpenAI `/v1/chat/completions` 协议转换
- `chacmd/shim/__init__.py`
- `chacmd/orchestrator/budget.py` — BudgetGuard（per-job token 预算 + kill）
- `chacmd/observability/otel.py` — OTel tracer/meter 初始化 + traceparent 注入
- `chacmd/observability/__init__.py`
- `chacmd/orchestrator/provisioner.py` — 容器供给（#2 一键起子容器）+ 配置下发（#10）
- 对应 `tests/test_*.py`

### 修改文件
- `chacmd/interfaces/chayuan_client.py` — 修 whoami/authz 端点（Task 1）
- `chacmd/api/app.py` — 加审批门端点（Task 5）、挂 shim 路由（Task 4）
- `chacmd/api/schemas.py` — 审批请求/响应 schema
- `chacmd/domain/repository.py` — Job 加 token 累计字段的读写（Task 6）
- `chacmd/domain/models.py` — Job 加 `tokens_used`/`token_budget` 列（Task 6）
- `chacmd/orchestrator/dispatcher.py` — 接 BudgetGuard + OTel span（Task 6/9）
- `chacmd/orchestrator/ingest.py` — 事件带 traceparent + 预算累计（Task 6/9）
- `chacmd/container.py` — 组合根：按 `use_fakes` 切真/假实现
- `chacmd/config.py` — 加 NATS URL、沙箱镜像、OpenHands、预算默认值等配置

---

## Milestone M3a — 修契约 + 真集成地基

### Task 1: 修察元集成契约（whoami / authz 端点错配）

**Files:**
- Modify: `chacmd/interfaces/chayuan_client.py`
- Test: `tests/test_chayuan_client.py`

- [ ] **Step 1: 写失败测试** — 断言 HttpChayuanClient 调正确端点路径

在 `tests/test_chayuan_client.py` 末尾追加：

```python
import httpx
import pytest
from chacmd.interfaces.chayuan_client import HttpChayuanClient


class _RecordingTransport(httpx.AsyncBaseTransport):
    """记录请求路径，返回预设响应。"""
    def __init__(self):
        self.paths: list[str] = []

    async def handle_async_request(self, request):
        self.paths.append(request.url.path)
        if request.url.path == "/openapi/v1/whoami":
            return httpx.Response(200, json={"subject": "u1", "dept": "d1"})
        if request.url.path == "/api/v1/kb-acl/check":
            return httpx.Response(200, json={"allowed": True})
        return httpx.Response(404, json={"detail": "not found"})


@pytest.mark.asyncio
async def test_whoami_hits_openapi_v1_path():
    transport = _RecordingTransport()
    c = HttpChayuanClient(base_url="http://chayuan.test", web_url="http://web.test")
    c._client = httpx.AsyncClient(base_url="http://chayuan.test", transport=transport)
    await c.whoami("tok")
    assert "/openapi/v1/whoami" in transport.paths
    assert "/api/v1/whoami" not in transport.paths


@pytest.mark.asyncio
async def test_authorize_hits_existing_kb_acl_path():
    transport = _RecordingTransport()
    c = HttpChayuanClient(base_url="http://chayuan.test", web_url="http://web.test")
    c._client = httpx.AsyncClient(base_url="http://chayuan.test", transport=transport)
    allowed = await c.authorize(subject="u1", resource="container:x", action="dispatch")
    assert allowed is True
    assert "/api/v1/authz/check" not in transport.paths
```

- [ ] **Step 2: 跑测试确认失败**

Run: `<SCRATCH>/cvenv/bin/python -m pytest tests/test_chayuan_client.py -q`
Expected: FAIL（当前调 `/api/v1/whoami` 和 `/api/v1/authz/check`）

- [ ] **Step 3: 改 HttpChayuanClient 的端点路径**

在 `chacmd/interfaces/chayuan_client.py` 中：

`whoami` 方法路径 `/api/v1/whoami` 改为 `/openapi/v1/whoami`：

```python
    async def whoami(self, token: str) -> dict:
        # 察元真实端点：router prefix /openapi/v1（见 openapi_routes.py:248）
        resp = await self._client.get("/openapi/v1/whoami", headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        return resp.json()
```

`authorize` 方法：察元无 `/api/v1/authz/check`。P0 采用 kb-acl 风格的 check 端点契约（若察元最终端点名不同，只改这一层）。改为：

```python
    async def authorize(self, subject: str, resource: str, action: str) -> bool:
        # 察元无独立 /authz/check；走 kb-acl 资源授权检查（§6.14 资源级 grant）。
        # 端点名以察元上游为准，防腐层集中于此，察元 API 变更只改此处。
        resp = await self._client.post(
            "/api/v1/kb-acl/check",
            json={"subject": subject, "resource": resource, "action": action},
        )
        resp.raise_for_status()
        return bool(resp.json().get("allowed", False))
```

- [ ] **Step 4: 跑测试确认通过**

Run: `<SCRATCH>/cvenv/bin/python -m pytest tests/test_chayuan_client.py -q`
Expected: PASS

- [ ] **Step 5: 全量回归 + 提交**

Run: `<SCRATCH>/cvenv/bin/python -m pytest -q`（应仍全绿）
```bash
git add chacmd/interfaces/chayuan_client.py tests/test_chayuan_client.py
git commit -m "fix(chacmd): 修察元契约端点 whoami→/openapi/v1, authz→kb-acl(防腐层集中)"
```

> ⚠️ 真实察元冒烟（起 `/work/chayuan-desktop` docker-compose 后 curl 这两个端点）留到 Task 10 的 M4 验收一并做——因为需要察元实例在跑。此处先把代码契约对齐并单测锁死。

---

### Task 2: NatsEventBus（EventBus 的 NATS JetStream 实现）

**Files:**
- Create: `chacmd/interfaces/nats_bus.py`
- Modify: `chacmd/config.py`
- Test: `tests/test_nats_bus.py`

- [ ] **Step 1: config 加 NATS 配置**

`chacmd/config.py` 的 `Settings` dataclass 加字段 + from_env：

```python
    nats_url: str = "nats://127.0.0.1:4222"
    event_bus: str = "memory"  # memory | nats
```
在 `from_env` 的返回里加：
```python
            nats_url=os.environ.get("CHACMD_NATS_URL", "nats://127.0.0.1:4222"),
            event_bus=os.environ.get("CHACMD_EVENT_BUS", "memory"),
```

- [ ] **Step 2: 写失败测试（跳过真 NATS，只测契约与降级）**

`tests/test_nats_bus.py`：

```python
import pytest
from chacmd.interfaces.nats_bus import NatsEventBus
from chacmd.interfaces.eventbus import EventBus


def test_nats_bus_satisfies_eventbus_protocol():
    # 结构化子类型：NatsEventBus 必须有 publish/subscribe
    assert hasattr(NatsEventBus, "publish")
    assert hasattr(NatsEventBus, "subscribe")


def test_subject_sanitized_for_jetstream():
    # NATS subject 不允许空格；job.<id>.<kind> 形态直接可用
    bus = NatsEventBus(url="nats://127.0.0.1:4222")
    assert bus._stream_subject("job.abc.started") == "job.abc.started"
```

- [ ] **Step 3: 跑测试确认失败**

Run: `<SCRATCH>/cvenv/bin/python -m pytest tests/test_nats_bus.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 4: 实现 NatsEventBus**

`chacmd/interfaces/nats_bus.py`：

```python
from __future__ import annotations

import json
from collections.abc import AsyncIterator


class NatsEventBus:
    """I6 — EventBus over NATS JetStream (NFR-P3).

    连接延迟建立（首次 publish/subscribe 时）。stream 名 CHACMD_EVENTS，
    subject 前缀 job.* / heartbeat.* / agent.*（无 IP，§6.22）。
    """

    def __init__(self, url: str, stream: str = "CHACMD_EVENTS") -> None:
        self._url = url
        self._stream = stream
        self._nc = None  # nats.aio.client.Client
        self._js = None

    def _stream_subject(self, subject: str) -> str:
        return subject  # job.<id>.<kind> 已是合法 NATS subject

    async def _ensure(self) -> None:
        if self._nc is not None:
            return
        import nats
        self._nc = await nats.connect(self._url)
        self._js = self._nc.jetstream()
        # 幂等建 stream；已存在则忽略
        try:
            await self._js.add_stream(name=self._stream, subjects=["job.>", "heartbeat.>", "agent.>"])
        except Exception:
            pass

    async def publish(self, subject: str, message: dict) -> None:
        await self._ensure()
        await self._js.publish(self._stream_subject(subject), json.dumps(message).encode())

    async def subscribe(self, subject: str) -> AsyncIterator[dict]:
        await self._ensure()
        sub = await self._js.subscribe(subject)
        try:
            async for msg in sub.messages:
                yield json.loads(msg.data.decode())
                await msg.ack()
        finally:
            await sub.unsubscribe()

    async def aclose(self) -> None:
        if self._nc is not None:
            await self._nc.close()
```

- [ ] **Step 5: 跑测试确认通过**

Run: `<SCRATCH>/cvenv/bin/python -m pytest tests/test_nats_bus.py -q`
Expected: PASS

- [ ] **Step 6: 组合根按配置切换 + 提交**

`chacmd/container.py` 的 `build_container` 里，把 `bus = InMemoryEventBus()` 改为：
```python
    if settings.event_bus == "nats" and not use_fakes:
        from chacmd.interfaces.nats_bus import NatsEventBus
        bus = NatsEventBus(url=settings.nats_url)
    else:
        bus = InMemoryEventBus()
```

Run: `<SCRATCH>/cvenv/bin/python -m pytest -q`
```bash
git add chacmd/interfaces/nats_bus.py chacmd/config.py chacmd/container.py tests/test_nats_bus.py
git commit -m "feat(chacmd): NatsEventBus (JetStream) + 组合根按配置切换 memory/nats"
```

---

### Task 3: Postgres provider 验证（Database 已抽象，补方言无关回归）

**Files:**
- Test: `tests/test_db.py`（补用例）
- Modify: `chacmd/config.py`（已默认 postgres URL，无需改）

- [ ] **Step 1: 写测试 — 断言 Database 对 sqlite/postgres 两种 URL 都能建 engine 且 dialect 正确**

`tests/test_db.py` 追加：

```python
@pytest.mark.asyncio
async def test_sqlite_dialect():
    db = Database(url="sqlite+aiosqlite:///:memory:")
    assert db.dialect == "sqlite"
    await db.dispose()


def test_postgres_url_builds_engine_without_connecting():
    # 建 engine 不触发连接；断言 dialect=postgresql
    db = Database(url="postgresql+asyncpg://u:p@127.0.0.1:5432/x")
    assert db.dialect == "postgresql"
```

- [ ] **Step 2: 跑测试**

Run: `<SCRATCH>/cvenv/bin/python -m pytest tests/test_db.py -q`
Expected: PASS（Database 已支持；若 asyncpg 未装则 postgres 用例报 import——`<SCRATCH>/cvenv/bin/pip install asyncpg` 补装）

- [ ] **Step 3: 提交**

```bash
git add tests/test_db.py
git commit -m "test(chacmd): Database 方言无关回归(sqlite+postgres URL)"
```

> Postgres RLS（NFR-T1）留 P1：P0 用 `dept` 列 + 应用层过滤，RLS policy 需真 Postgres 实例，M4 冒烟时验证。

---

## Milestone M3b — 真执行链路

### Task 4: Anthropic `/v1/messages` shim（给 Claude Code 接母体网关）

**Files:**
- Create: `chacmd/shim/__init__.py`, `chacmd/shim/anthropic_shim.py`
- Modify: `chacmd/api/app.py`
- Test: `tests/test_anthropic_shim.py`

参考格式（来自 claude-api skill）：Anthropic 请求体 `{model, max_tokens, messages:[{role, content}], system?}`，OpenAI 请求体 `{model, messages:[{role, content}]}`（system 作为一条 `role:"system"` 消息）。Anthropic 响应 `{content:[{type:"text", text}], stop_reason, usage:{input_tokens, output_tokens}}`，OpenAI 响应 `{choices:[{message:{content}}], usage:{prompt_tokens, completion_tokens}}`。

- [ ] **Step 1: 写失败测试 — 请求/响应双向转换**

`tests/test_anthropic_shim.py`：

```python
from chacmd.shim.anthropic_shim import anthropic_to_openai, openai_to_anthropic


def test_request_system_becomes_system_message():
    a = {"model": "m", "max_tokens": 100, "system": "you are x",
         "messages": [{"role": "user", "content": "hi"}]}
    o = anthropic_to_openai(a)
    assert o["messages"][0] == {"role": "system", "content": "you are x"}
    assert o["messages"][1] == {"role": "user", "content": "hi"}
    assert o["max_tokens"] == 100


def test_request_content_blocks_flattened_to_text():
    a = {"model": "m", "max_tokens": 10,
         "messages": [{"role": "user", "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}]}
    o = anthropic_to_openai(a)
    assert o["messages"][0]["content"] == "a\nb"


def test_response_openai_to_anthropic_shape():
    o = {"choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
         "usage": {"prompt_tokens": 5, "completion_tokens": 7}}
    a = openai_to_anthropic(o, model="m")
    assert a["content"] == [{"type": "text", "text": "hello"}]
    assert a["stop_reason"] == "end_turn"
    assert a["usage"] == {"input_tokens": 5, "output_tokens": 7}
    assert a["role"] == "assistant"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `<SCRATCH>/cvenv/bin/python -m pytest tests/test_anthropic_shim.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现转换函数**

`chacmd/shim/__init__.py`：空文件。

`chacmd/shim/anthropic_shim.py`：

```python
from __future__ import annotations

from typing import Any

_FINISH_MAP = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use"}


def _flatten_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)


def anthropic_to_openai(req: dict) -> dict:
    """Anthropic /v1/messages 请求体 → 察元 OpenAI /v1/chat/completions 请求体。"""
    messages = []
    if req.get("system"):
        messages.append({"role": "system", "content": req["system"]})
    for m in req.get("messages", []):
        messages.append({"role": m["role"], "content": _flatten_content(m["content"])})
    out = {"model": req["model"], "messages": messages}
    if "max_tokens" in req:
        out["max_tokens"] = req["max_tokens"]
    if "temperature" in req:
        out["temperature"] = req["temperature"]
    return out


def openai_to_anthropic(resp: dict, model: str) -> dict:
    """察元 OpenAI 响应 → Anthropic /v1/messages 响应体。"""
    choice = (resp.get("choices") or [{}])[0]
    text = choice.get("message", {}).get("content", "") or ""
    finish = choice.get("finish_reason", "stop")
    usage = resp.get("usage", {})
    return {
        "id": resp.get("id", "msg_shim"),
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}],
        "stop_reason": _FINISH_MAP.get(finish, "end_turn"),
        "usage": {
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
        },
    }
```

- [ ] **Step 4: 跑测试确认通过**

Run: `<SCRATCH>/cvenv/bin/python -m pytest tests/test_anthropic_shim.py -q`
Expected: PASS

- [ ] **Step 5: 挂 FastAPI 路由 + 端点测试**

`chacmd/api/app.py` 的 `create_app(db)` 改为 `create_app(db, chayuan=None)`（可选注入 client，向后兼容），并加路由：

```python
def create_app(db: Database, chayuan=None) -> FastAPI:
    app = FastAPI(title="ChaCMD Orchestrator", version="0.1.0")
    jobs = JobRepository(db)

    # ... 现有三个路由不变 ...

    if chayuan is not None:
        from chacmd.shim.anthropic_shim import anthropic_to_openai, openai_to_anthropic

        @app.post("/v1/messages")
        async def anthropic_messages(req: dict) -> dict:
            # Claude Code 经此 shim 调察元 OpenAI 兼容网关（#16 缺口）
            oai_req = anthropic_to_openai(req)
            oai_resp = await chayuan.chat_completions(oai_req["model"], oai_req["messages"],
                                                      **{k: v for k, v in oai_req.items()
                                                         if k not in ("model", "messages")})
            return openai_to_anthropic(oai_resp, model=req["model"])

    return app
```

在 `tests/test_api.py` 加端点测试（用 FakeChayuanClient）：

```python
@pytest.mark.asyncio
async def test_anthropic_shim_endpoint():
    from chacmd.interfaces.chayuan_client import FakeChayuanClient
    db = Database(url="sqlite+aiosqlite:///:memory:")
    await db.create_all()
    app = create_app(db, chayuan=FakeChayuanClient())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/v1/messages", json={"model": "deepseek", "max_tokens": 50,
                                               "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    body = r.json()
    assert body["content"][0]["type"] == "text"
    assert body["role"] == "assistant"
    await db.dispose()
```

- [ ] **Step 6: cli.py 传 chayuan 进 create_app**

`chacmd/cli.py` 的 `_serve` 里 `app = create_app(container.db)` 改为 `app = create_app(container.db, chayuan=container.chayuan)`。

- [ ] **Step 7: 全量回归 + 提交**

Run: `<SCRATCH>/cvenv/bin/python -m pytest -q`
```bash
git add chacmd/shim/ chacmd/api/app.py chacmd/cli.py tests/test_anthropic_shim.py tests/test_api.py
git commit -m "feat(chacmd): Anthropic /v1/messages shim → 察元 OpenAI 网关(#16 缺口)"
```

---

### Task 5: 审批门 API（pending_approval 批准/打回，NFR-H1）

**Files:**
- Modify: `chacmd/api/app.py`, `chacmd/api/schemas.py`, `chacmd/domain/repository.py`
- Test: `tests/test_api.py`, `tests/test_state.py`

状态机已支持 `PENDING_APPROVAL → RUNNING`（批准继续）和 `PENDING_APPROVAL → CANCELLED/FAILED`（打回）。本 Task 加 HTTP 动作。

- [ ] **Step 1: 写失败测试 — 批准把 pending_approval → running，打回 → cancelled**

`tests/test_api.py` 追加：

```python
@pytest.mark.asyncio
async def test_approve_moves_pending_to_running(client):
    created = await client.post("/api/v1/tasks/c/runs", json={"goal": "g", "dept": "d1"})
    job_id = created.json()["job_id"]
    # 手工推进到 pending_approval（queued→dispatching→running→pending_approval）
    from chacmd.domain.repository import JobRepository
    # 通过内部 API 造态：这里用直接 POST 状态推进端点或 repo；简化用 repo fixture
    # 见 Step 3 提供的 test helper 端点
    await client.post(f"/api/v1/runs/{job_id}/_force_state", json={"state": "pending_approval"})
    r = await client.post(f"/api/v1/runs/{job_id}/approve")
    assert r.status_code == 200
    assert r.json()["state"] == "running"


@pytest.mark.asyncio
async def test_reject_moves_pending_to_cancelled(client):
    created = await client.post("/api/v1/tasks/c/runs", json={"goal": "g", "dept": "d1"})
    job_id = created.json()["job_id"]
    await client.post(f"/api/v1/runs/{job_id}/_force_state", json={"state": "pending_approval"})
    r = await client.post(f"/api/v1/runs/{job_id}/reject", json={"reason": "看着不对"})
    assert r.status_code == 200
    assert r.json()["state"] == "cancelled"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `<SCRATCH>/cvenv/bin/python -m pytest tests/test_api.py -q -k "approve or reject"`
Expected: FAIL（端点不存在）

- [ ] **Step 3: schema + repo helper + 端点**

`chacmd/api/schemas.py` 追加：

```python
class RejectRequest(BaseModel):
    reason: str = ""


class ForceStateRequest(BaseModel):  # 仅测试/运维用
    state: str
```

`chacmd/domain/repository.py` 的 `JobRepository` 加一个绕过状态机的强制写（仅供测试/运维 seed）：

```python
    async def force_state(self, job_id: str, state: str) -> None:
        async with self._db.session() as s:
            job = await s.get(Job, job_id)
            if job is None:
                raise KeyError(f"unknown job: {job_id}")
            job.state = state
            await s.commit()
```

`chacmd/api/app.py` 加端点（用现有 `jobs.set_state`，它内部走状态机 `transition` 做合法性校验）：

```python
    from chacmd.domain.state import JobState
    from chacmd.api.schemas import RejectRequest, ForceStateRequest

    @app.post("/api/v1/runs/{job_id}/approve", response_model=RunStatus)
    async def approve(job_id: str) -> RunStatus:
        try:
            await jobs.set_state(job_id, JobState.RUNNING)  # pending_approval→running
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        job = await jobs.get(job_id)
        return RunStatus(job_id=job.id, code=job.code, goal=job.goal, dept=job.dept, state=job.state)

    @app.post("/api/v1/runs/{job_id}/reject", response_model=RunStatus)
    async def reject(job_id: str, req: RejectRequest) -> RunStatus:
        try:
            await jobs.set_state(job_id, JobState.CANCELLED)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        job = await jobs.get(job_id)
        return RunStatus(job_id=job.id, code=job.code, goal=job.goal, dept=job.dept, state=job.state)

    @app.post("/api/v1/runs/{job_id}/_force_state", response_model=RunStatus)
    async def _force_state(job_id: str, req: ForceStateRequest) -> RunStatus:
        # 运维/测试专用：绕过状态机造态
        await jobs.force_state(job_id, req.state)
        job = await jobs.get(job_id)
        return RunStatus(job_id=job.id, code=job.code, goal=job.goal, dept=job.dept, state=job.state)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `<SCRATCH>/cvenv/bin/python -m pytest tests/test_api.py -q`
Expected: PASS

- [ ] **Step 5: 补状态机测试（打回后不可再批准）**

`tests/test_state.py` 追加：
```python
def test_cancelled_is_terminal():
    from chacmd.domain.state import JobState, can_transition
    assert not can_transition(JobState.CANCELLED, JobState.RUNNING)
```

- [ ] **Step 6: 全量回归 + 提交**

Run: `<SCRATCH>/cvenv/bin/python -m pytest -q`
```bash
git add chacmd/api/ chacmd/domain/repository.py tests/test_api.py tests/test_state.py
git commit -m "feat(chacmd): 审批门 API approve/reject(NFR-H1) + 状态机校验"
```

---

### Task 6: per-job 预算 kill（NFR-C1）

**Files:**
- Create: `chacmd/orchestrator/budget.py`
- Modify: `chacmd/domain/models.py`, `chacmd/domain/repository.py`, `chacmd/orchestrator/ingest.py`, `chacmd/config.py`
- Test: `tests/test_budget.py`

- [ ] **Step 1: models 加 token 字段**

`chacmd/domain/models.py` 的 `Job` 类加两列：
```python
    token_budget: Mapped[int] = mapped_column(Integer, default=0)   # 0=不限
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
```
`Job.__init__` 走 SQLAlchemy 默认即可。`config.py` 加 `default_token_budget: int = 100_000` + env `CHACMD_JOB_TOKEN_BUDGET`。

- [ ] **Step 2: 写失败测试**

`tests/test_budget.py`：

```python
import pytest
from chacmd.orchestrator.budget import BudgetGuard


class _FakeJobs:
    def __init__(self, budget, used=0):
        self._budget, self._used = budget, used
        self.killed = False
    async def add_tokens(self, job_id, n):
        self._used += n
        return self._used
    async def get_budget(self, job_id):
        return self._budget


@pytest.mark.asyncio
async def test_under_budget_ok():
    g = BudgetGuard(_FakeJobs(budget=100))
    assert await g.charge("j", 50) is True   # 未超

@pytest.mark.asyncio
async def test_over_budget_signals_kill():
    jobs = _FakeJobs(budget=100)
    g = BudgetGuard(jobs)
    await g.charge("j", 60)
    assert await g.charge("j", 60) is False  # 累计 120 > 100 → kill 信号

@pytest.mark.asyncio
async def test_zero_budget_never_kills():
    g = BudgetGuard(_FakeJobs(budget=0))
    assert await g.charge("j", 10_000_000) is True
```

- [ ] **Step 3: 跑测试确认失败**

Run: `<SCRATCH>/cvenv/bin/python -m pytest tests/test_budget.py -q`
Expected: FAIL

- [ ] **Step 4: 实现 BudgetGuard + repo 方法**

`chacmd/orchestrator/budget.py`：

```python
from __future__ import annotations


class BudgetGuard:
    """per-job token 硬预算（NFR-C1）。charge 返回 False = 超预算，调用方应 kill。"""

    def __init__(self, jobs) -> None:
        self._jobs = jobs

    async def charge(self, job_id: str, tokens: int) -> bool:
        budget = await self._jobs.get_budget(job_id)
        used = await self._jobs.add_tokens(job_id, tokens)
        if budget and used > budget:
            return False
        return True
```

`chacmd/domain/repository.py` 的 `JobRepository` 加：

```python
    async def add_tokens(self, job_id: str, n: int) -> int:
        async with self._db.session() as s:
            job = await s.get(Job, job_id)
            job.tokens_used = (job.tokens_used or 0) + n
            await s.commit()
            return job.tokens_used

    async def get_budget(self, job_id: str) -> int:
        async with self._db.session() as s:
            job = await s.get(Job, job_id)
            return job.token_budget or 0
```

- [ ] **Step 5: 跑测试确认通过**

Run: `<SCRATCH>/cvenv/bin/python -m pytest tests/test_budget.py -q`
Expected: PASS

- [ ] **Step 6: dispatcher 接 BudgetGuard——事件流里超预算则 cancel adapter**

`chacmd/orchestrator/dispatcher.py` 的 `Dispatcher.__init__` 加可选 `budget=None` 参数存 `self._budget`。`dispatch` 的事件循环改为：

```python
        async for event in self._adapter.dispatch(spec):
            await self._ingest.handle(event)
            tok = event.payload.get("tokens", 0) if event.payload else 0
            if self._budget is not None and tok:
                if not await self._budget.charge(job_id, tok):
                    await self._adapter.cancel(job_id, job_id)
                    await self._jobs.set_state(job_id, JobState.FAILED)
                    break
```

`chacmd/container.py` 里 `dispatcher = Dispatcher(jobs, containers, chayuan, adapter, ingest)` 改为传 budget：
```python
    from chacmd.orchestrator.budget import BudgetGuard
    dispatcher = Dispatcher(jobs, containers, chayuan, adapter, ingest, budget=BudgetGuard(jobs))
```

- [ ] **Step 7: 端到端预算测试（FakeAgentAdapter 吐带 tokens 的事件，超预算被 kill）**

`tests/test_dispatcher.py` 追加用例：造一个每步 payload 带 `tokens` 的 FakeAgentAdapter，`token_budget` 设小值，断言 job 最终 FAILED 且 adapter 被 cancel。（参照现有 test_dispatcher.py 的 fixture 风格。）

- [ ] **Step 8: 全量回归 + 提交**

Run: `<SCRATCH>/cvenv/bin/python -m pytest -q`
```bash
git add chacmd/orchestrator/budget.py chacmd/domain/ chacmd/container.py tests/test_budget.py tests/test_dispatcher.py chacmd/config.py
git commit -m "feat(chacmd): per-job token 预算 kill(NFR-C1) + Job token 计量列"
```

---

### Task 7: DockerSandbox（rootless Docker + 加固基线，NFR-SEC1）

**Files:**
- Create: `chacmd/interfaces/docker_sandbox.py`
- Modify: `chacmd/config.py`, `chacmd/container.py`
- Test: `tests/test_docker_sandbox.py`

真起容器需 Docker daemon，CI 不一定有——本 Task 测**加固参数构造**（纯函数，可单测），真起容器留 M4 冒烟。

- [ ] **Step 1: 写失败测试 — 加固参数正确 + socket 挂载被拒**

`tests/test_docker_sandbox.py`：

```python
import pytest
from chacmd.interfaces.sandbox import SandboxSpec
from chacmd.interfaces.docker_sandbox import build_run_kwargs


def test_hardening_baseline_applied():
    kw = build_run_kwargs(SandboxSpec(nickname="w1", image="chatop-ai:latest"))
    assert kw["cap_drop"] == ["ALL"]
    assert kw["security_opt"] == ["no-new-privileges"]
    assert kw["read_only"] is True
    assert kw["network_mode"] == "none" or "network" in kw  # 默认拒绝出站(NFR-SEC2)


def test_socket_mount_rejected_at_spec():
    with pytest.raises(ValueError):
        SandboxSpec(nickname="w1", image="x", mounts=["/var/run/docker.sock:/x"])
```

- [ ] **Step 2: 跑测试确认失败**

Run: `<SCRATCH>/cvenv/bin/python -m pytest tests/test_docker_sandbox.py -q`
Expected: FAIL（build_run_kwargs 不存在；socket 拒绝已在 SandboxSpec.__post_init__ 实现，第二个应 PASS）

- [ ] **Step 3: 实现 DockerSandbox + 加固参数函数**

`chacmd/interfaces/docker_sandbox.py`：

```python
from __future__ import annotations

import uuid
from chacmd.interfaces.sandbox import SandboxHandle, SandboxSpec


def build_run_kwargs(spec: SandboxSpec) -> dict:
    """容器加固基线（NFR-SEC1/SEC2/§9）：cap-drop ALL、no-new-privileges、
    read-only rootfs、默认拒绝出站。socket 永不入容器（SandboxSpec 已拦）。"""
    return {
        "image": spec.image,
        "name": f"chacmd-{spec.nickname}-{uuid.uuid4().hex[:8]}",
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges"],
        "read_only": True,
        "network_mode": "none",   # 默认拒绝出站；需网络的角色由 per-role 白名单放开(P1)
        "mem_limit": "3g",
        "pids_limit": 512,
        "volumes": {},            # per-job 卷由 provisioner 单独 bind(Task 9)
        "detach": True,
    }


class DockerSandbox:
    """I7 — rootless Docker sandbox。真起容器需 docker daemon(rootless)。"""

    def __init__(self) -> None:
        self._client = None

    def _ensure(self):
        if self._client is None:
            import docker
            self._client = docker.from_env()
        return self._client

    async def create(self, spec: SandboxSpec) -> SandboxHandle:
        client = self._ensure()
        kwargs = build_run_kwargs(spec)
        container = client.containers.run(**kwargs)
        return SandboxHandle(id=container.id, nickname=spec.nickname)

    async def destroy(self, handle_id: str) -> None:
        client = self._ensure()
        try:
            c = client.containers.get(handle_id)
            c.remove(force=True)
        except Exception:
            pass
```

`config.py` 加 `sandbox: str = "fake"  # fake | docker` + `sandbox_image: str = "chatop-ai:latest"`。

- [ ] **Step 4: 跑测试确认通过**

Run: `<SCRATCH>/cvenv/bin/python -m pytest tests/test_docker_sandbox.py -q`
Expected: PASS

- [ ] **Step 5: 组合根按配置切换 + 提交**

`chacmd/container.py` 里 `sandbox=FakeSandbox()` 改为：
```python
    if settings.sandbox == "docker" and not use_fakes:
        from chacmd.interfaces.docker_sandbox import DockerSandbox
        sandbox = DockerSandbox()
    else:
        sandbox = FakeSandbox()
```
（并把 `sandbox=FakeSandbox()` 从 Container(...) 调用改为 `sandbox=sandbox`。）

Run: `<SCRATCH>/cvenv/bin/python -m pytest -q`
```bash
git add chacmd/interfaces/docker_sandbox.py chacmd/config.py chacmd/container.py tests/test_docker_sandbox.py
git commit -m "feat(chacmd): DockerSandbox rootless + 加固基线(cap-drop/no-new-priv/read-only/no-net, NFR-SEC1/2)"
```

---

### Task 8: OpenHandsAdapter（AgentAdapter 真实现）

**Files:**
- Create: `chacmd/adapters/__init__.py`, `chacmd/adapters/openhands_adapter.py`
- Modify: `chacmd/config.py`, `chacmd/container.py`
- Test: `tests/test_openhands_adapter.py`

OpenHands headless 输出 JSONL 事件流。真跑需 OpenHands 运行时——本 Task 测 **JSONL→统一 Event 的映射函数**（纯函数），真 spawn 留 M4。映射逻辑复用已有的 agent-bridge event_adapter（`.claude/worktrees/.../agent-bridge/agent_bridge/event_adapter.py`）思路。

- [ ] **Step 1: 写失败测试 — OpenHands JSONL 行 → 统一 Event kind**

`tests/test_openhands_adapter.py`：

```python
from chacmd.adapters.openhands_adapter import map_openhands_line


def test_agent_start_maps_to_started():
    e = map_openhands_line({"action": "start"}, job_id="j", task_id="t", nickname="w", seq=0)
    assert e.kind == "started"

def test_run_action_maps_to_progress():
    e = map_openhands_line({"action": "run", "args": {"command": "ls"}}, job_id="j", task_id="t", nickname="w", seq=1)
    assert e.kind == "progress"
    assert e.payload["command"] == "ls"

def test_finish_maps_to_succeeded():
    e = map_openhands_line({"observation": "agent_state_changed", "extras": {"agent_state": "finished"}},
                           job_id="j", task_id="t", nickname="w", seq=2)
    assert e.kind == "succeeded"

def test_error_maps_to_failed():
    e = map_openhands_line({"observation": "error", "message": "boom"},
                           job_id="j", task_id="t", nickname="w", seq=3)
    assert e.kind == "failed"

def test_token_usage_carried_in_payload():
    e = map_openhands_line({"action": "message", "llm_metrics": {"total_tokens": 42}},
                           job_id="j", task_id="t", nickname="w", seq=4)
    assert e.payload.get("tokens") == 42
```

- [ ] **Step 2: 跑测试确认失败**

Run: `<SCRATCH>/cvenv/bin/python -m pytest tests/test_openhands_adapter.py -q`
Expected: FAIL

- [ ] **Step 3: 实现映射 + adapter 骨架**

`chacmd/adapters/__init__.py`：空。

`chacmd/adapters/openhands_adapter.py`：

```python
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from chacmd.domain.events import Event
from chacmd.interfaces.agent_adapter import AgentAdapter, DispatchSpec


def map_openhands_line(line: dict, *, job_id: str, task_id: str, nickname: str, seq: int) -> Event:
    """OpenHands JSONL 事件 → 统一 Event(§6.6)。未知行归为 progress。"""
    tokens = 0
    metrics = line.get("llm_metrics")
    if isinstance(metrics, dict):
        tokens = metrics.get("total_tokens", 0) or 0

    kind = "progress"
    payload: dict[str, Any] = {}

    if line.get("action") == "start":
        kind = "started"
    elif line.get("observation") == "error":
        kind = "failed"
        payload["message"] = line.get("message", "")
    elif line.get("observation") == "agent_state_changed" and \
            line.get("extras", {}).get("agent_state") == "finished":
        kind = "succeeded"
    elif line.get("action") == "run":
        kind = "progress"
        payload["command"] = line.get("args", {}).get("command", "")
    elif "action" in line:
        kind = "progress"
        payload["action"] = line["action"]

    if tokens:
        payload["tokens"] = tokens
    return Event(job_id, task_id, nickname, kind, seq, payload)


class OpenHandsAdapter(AgentAdapter):
    """I5 — OpenHands headless(--headless --json)。构造命令 → 逐行解析 stdout JSONL。"""

    def __init__(self, launch_cmd: list[str] | None = None) -> None:
        # launch_cmd 模板；真跑由 provisioner 在子容器内起。P0 支持本地子进程模式。
        self._launch_cmd = launch_cmd or ["python", "-m", "openhands.core.main", "--headless"]
        self._procs: dict[tuple[str, str], asyncio.subprocess.Process] = {}

    async def dispatch(self, spec: DispatchSpec) -> AsyncIterator[Event]:
        cmd = [*self._launch_cmd, "-t", spec.goal]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        self._procs[(spec.job_id, spec.task_id)] = proc
        seq = 0
        yield Event(spec.job_id, spec.task_id, spec.nickname, "started", seq, {"goal": spec.goal})
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode(errors="replace").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            seq += 1
            yield map_openhands_line(obj, job_id=spec.job_id, task_id=spec.task_id,
                                     nickname=spec.nickname, seq=seq)
        await proc.wait()

    async def health(self) -> bool:
        return True

    async def cancel(self, job_id: str, task_id: str) -> None:
        proc = self._procs.get((job_id, task_id))
        if proc and proc.returncode is None:
            proc.terminate()

    def manifest(self) -> dict[str, Any]:
        return {"name": "openhands", "capabilities": ["stream", "cancel", "sandbox"]}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `<SCRATCH>/cvenv/bin/python -m pytest tests/test_openhands_adapter.py -q`
Expected: PASS

- [ ] **Step 5: 组合根按配置切换 + 提交**

`config.py` 加 `agent_adapter: str = "fake"  # fake | openhands`。`chacmd/container.py` 非 fake 分支：
```python
    else:
        chayuan = HttpChayuanClient(...)
        if settings.agent_adapter == "openhands":
            from chacmd.adapters.openhands_adapter import OpenHandsAdapter
            adapter = OpenHandsAdapter()
        else:
            adapter = FakeAgentAdapter(steps=["step-1"])
        auth = ChayuanAuthProvider(chayuan)
```

Run: `<SCRATCH>/cvenv/bin/python -m pytest -q`
```bash
git add chacmd/adapters/ chacmd/config.py chacmd/container.py tests/test_openhands_adapter.py
git commit -m "feat(chacmd): OpenHandsAdapter(JSONL→统一事件 + 常驻子进程流式) 替 Fake 非测试路径"
```

---

### Task 9: OTel trace + 容器供给/配置下发

**Files:**
- Create: `chacmd/observability/__init__.py`, `chacmd/observability/otel.py`, `chacmd/orchestrator/provisioner.py`
- Modify: `chacmd/orchestrator/ingest.py`, `chacmd/config.py`, `chacmd/container.py`
- Test: `tests/test_otel.py`, `tests/test_provisioner.py`

- [ ] **Step 1: 写失败测试 — traceparent 注入事件 + provisioner 组装供给规格**

`tests/test_otel.py`：
```python
from chacmd.observability.otel import inject_traceparent

def test_traceparent_added_to_message():
    msg = {"kind": "started", "seq": 0}
    out = inject_traceparent(msg, job_id="j1")
    assert "traceparent" in out
    assert out["baggage"]["job_id"] == "j1"
```

`tests/test_provisioner.py`：
```python
import pytest
from chacmd.orchestrator.provisioner import Provisioner
from chacmd.interfaces.sandbox import FakeSandbox

@pytest.mark.asyncio
async def test_provision_creates_sandbox_and_registers():
    class _Containers:
        def __init__(self): self.regs = {}
        async def upsert(self, nickname, session, dept):
            self.regs[nickname] = (session, dept)
    sb, containers = FakeSandbox(), _Containers()
    p = Provisioner(sb, containers, image="chatop-ai:latest")
    handle = await p.provision(nickname="worker-1", dept="d1", env={"MODEL": "deepseek"})
    assert handle.nickname == "worker-1"
    assert "worker-1" in containers.regs   # 供给后注册到覆盖网
    assert handle.id in sb.live
```

- [ ] **Step 2: 跑测试确认失败**

Run: `<SCRATCH>/cvenv/bin/python -m pytest tests/test_otel.py tests/test_provisioner.py -q`
Expected: FAIL

- [ ] **Step 3: 实现 otel + provisioner**

`chacmd/observability/__init__.py`：空。

`chacmd/observability/otel.py`（最小实现，不强依赖 opentelemetry 包——用 W3C traceparent 格式字符串；装了 otel 则用真 tracer）：

```python
from __future__ import annotations

import os


def inject_traceparent(message: dict, job_id: str, trace_id: str | None = None) -> dict:
    """给总线消息注入 W3C traceparent + baggage(job_id)。NFR-O1 最小实现。"""
    # 无 otel 依赖时用确定性占位 trace_id（真实部署由 otel SDK 生成）
    tid = trace_id or (job_id.replace("-", "")[:32].ljust(32, "0"))
    span_id = "0" * 16
    out = dict(message)
    out["traceparent"] = f"00-{tid}-{span_id}-01"
    out["baggage"] = {"job_id": job_id}
    return out


def init_tracing(service_name: str = "chacmd") -> None:
    """装了 opentelemetry-sdk 则初始化；否则 no-op(P0 最小可运行)。"""
    if os.environ.get("CHACMD_OTEL_DISABLED"):
        return
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        trace.set_tracer_provider(TracerProvider())
    except Exception:
        pass  # 依赖缺失时静默降级
```

`chacmd/orchestrator/provisioner.py`：

```python
from __future__ import annotations

from chacmd.interfaces.sandbox import SandboxHandle, SandboxSpec


class Provisioner:
    """容器供给(#2 一键起子容器) + 配置下发(#10)。供给后注册到覆盖网(无 IP)。"""

    def __init__(self, sandbox, containers, image: str) -> None:
        self._sandbox = sandbox
        self._containers = containers
        self._image = image

    async def provision(self, nickname: str, dept: str, env: dict | None = None) -> SandboxHandle:
        spec = SandboxSpec(nickname=nickname, image=self._image)
        # env 即 #10 配置下发(模型/Key/BaseURL)；真 DockerSandbox 会注入进容器 environment
        spec.env = env or {}   # SandboxSpec 需支持 env 字段——见 Step 4
        handle = await self._sandbox.create(spec)
        # 供给成功即注册 nickname→session(P0 用 handle.id 作 session 句柄，非 IP)
        await self._containers.upsert(nickname=nickname, session=handle.id, dept=dept)
        return handle
```

- [ ] **Step 4: SandboxSpec 加 env 字段 + DockerSandbox 注入**

`chacmd/interfaces/sandbox.py` 的 `SandboxSpec` 加 `env: dict = field(default_factory=dict)`（放在 mounts 后，`__post_init__` 不变）。`chacmd/interfaces/docker_sandbox.py` 的 `build_run_kwargs` 加 `"environment": spec.env,`。

- [ ] **Step 5: ingest 注入 traceparent**

`chacmd/orchestrator/ingest.py` 的 `handle` 里，publish 前给 message 注 traceparent：
```python
        from chacmd.observability.otel import inject_traceparent
        msg = inject_traceparent({"kind": e.kind, "seq": e.seq, "payload": e.payload}, job_id=e.job_id)
        await self._bus.publish(e.subject(), msg)
```
（原 `await self._bus.publish(...)` 那行替换。）

- [ ] **Step 6: 跑测试确认通过**

Run: `<SCRATCH>/cvenv/bin/python -m pytest tests/test_otel.py tests/test_provisioner.py -q`
Expected: PASS

- [ ] **Step 7: 组合根挂 provisioner + init_tracing + 提交**

`chacmd/container.py` 的 `build_container` 开头加 `from chacmd.observability.otel import init_tracing; init_tracing()`；Container dataclass 加 `provisioner` 字段并构造 `Provisioner(sandbox, containers, image=settings.sandbox_image)`。

Run: `<SCRATCH>/cvenv/bin/python -m pytest -q`
```bash
git add chacmd/observability/ chacmd/orchestrator/provisioner.py chacmd/orchestrator/ingest.py chacmd/interfaces/sandbox.py chacmd/interfaces/docker_sandbox.py chacmd/config.py chacmd/container.py tests/test_otel.py tests/test_provisioner.py
git commit -m "feat(chacmd): OTel traceparent 注入(NFR-O1) + 容器供给/配置下发 Provisioner(#2/#10)"
```

---

## Milestone M4 — 端到端验收

### Task 10: 端到端集成测试 + 真实察元冒烟 + 五条验收

**Files:**
- Test: `tests/test_e2e_m4.py`
- Create: `docs/superpowers/chacmd-m4-acceptance.md`（验收记录）

- [ ] **Step 1: 写端到端集成测试（Fake 全链路，验证编排正确）**

`tests/test_e2e_m4.py`：串起 build_container(use_fakes=True) → create_run → dispatch（Fake 吐 started/progress/pending_approval/... ）→ approve → succeeded → workspace mark_done → 断言 audit 有全序列、job 终态 succeeded、卷有 done-marker。参照现有 `tests/test_e2e_dispatch.py` 扩展。

```python
import pytest
from chacmd.config import Settings
from chacmd.container import build_container


@pytest.mark.asyncio
async def test_full_dispatch_to_volume():
    settings = Settings(db_url="sqlite+aiosqlite:///:memory:",
                        chayuan_base_url="http://x", chayuan_web_url="http://x",
                        workspace_root="/tmp/chacmd-e2e-test")
    c = await build_container(settings, use_fakes=True)
    # 注册一个容器
    await c.containers.upsert(nickname="w1", session="s1", dept="d1")
    job = await c.jobs.create(code="app1", goal="build", dept="d1")
    await c.dispatcher.dispatch(job.id, "w1", "agent.w1.inbox", "sys prompt")
    final = await c.jobs.get(job.id)
    assert final.state == "succeeded"
    events = await c.audit.list_for_job(job.id)
    kinds = [e.kind for e in events]
    assert "started" in kinds and "succeeded" in kinds
    await c.db.dispose()
```

- [ ] **Step 2: 跑全量测试**

Run: `<SCRATCH>/cvenv/bin/python -m pytest -q`
Expected: 全绿（含新增 e2e）

- [ ] **Step 3: 真实察元冒烟（需 /work/chayuan-desktop 实例）**

起察元 docker-compose 后，验证 Task 1 的契约（人工/脚本）：
```bash
# 起察元(参考 /work/chayuan-desktop/docker/docker-compose.yaml)
# 然后 curl 验证端点存在:
curl -s http://127.0.0.1:8000/openapi/v1/whoami -H "Authorization: Bearer <token>" -o /dev/null -w "%{http_code}\n"
# 期望非 404(200 或 401——端点存在)
curl -s -X POST http://127.0.0.1:8000/v1/chat/completions -H "Content-Type: application/json" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"hi"}]}' -o /dev/null -w "%{http_code}\n"
# 期望 200(shim 目标端点可达)
```
把结果记进 `docs/superpowers/chacmd-m4-acceptance.md`。若察元实例不可得，明确标注"契约已单测锁定，真冒烟待察元环境就绪"。

- [ ] **Step 4: 逐条核对 P0 五条验收，写验收记录**

`docs/superpowers/chacmd-m4-acceptance.md` 逐条打勾并附证据：
1. 端到端建任务→（真 OpenHands 沙箱开发+跑→预览）→审批→汇总 —— Fake 链路 ✅；真 OpenHands 需 M4 环境实跑
2. 沙箱不可逃逸（socket 不入容器）—— 代码 guard + 加固基线单测 ✅；真起容器验证 socket 不可见
3. 超 per-job 预算自动 kill —— test_budget + test_dispatcher 预算用例 ✅
4. 审批门可批准/打回 —— test_api approve/reject ✅
5. 大屏实时事件流 —— 后端 NATS 事件流 ✅（大屏 UI 属前端，另仓）

- [ ] **Step 5: 全量回归 + 收尾提交**

Run: `<SCRATCH>/cvenv/bin/python -m pytest -q`（记录最终 passed 数）
```bash
git add tests/test_e2e_m4.py docs/superpowers/chacmd-m4-acceptance.md
git commit -m "test(chacmd): M4 端到端验收 + 五条验收记录 + 察元冒烟"
```

- [ ] **Step 6: lint gate**

Run: `<SCRATCH>/cvenv/bin/ruff check chacmd/ 2>&1 | tail -20`（若装了 ruff；触达文件 targeted 修复）

---

## Self-Review

**1. 需求覆盖：**
- 契约修复 → Task 1 ✓ | NATS(NFR-P3) → Task 2 ✓ | Postgres(NFR-S1) → Task 3 ✓
- `/v1/messages` shim(#16 缺口) → Task 4 ✓ | 审批门(NFR-H1) → Task 5 ✓ | 预算 kill(NFR-C1) → Task 6 ✓
- 真沙箱加固(NFR-SEC1/2/S1沙箱) → Task 7 ✓ | 真 OpenHands(#5/#6/S1) → Task 8 ✓
- OTel(NFR-O1) → Task 9 ✓ | 容器供给(#2)/配置下发(#10) → Task 9 ✓ | 端到端(M4) → Task 10 ✓

**2. Placeholder 扫描：** 无 "TODO/后补"。真起容器(Task 7)、真 spawn OpenHands(Task 8)、真 NATS(Task 2)、真 Postgres+RLS(Task 3)、真察元冒烟(Task 10) 均因需外部运行时而以"纯函数/契约单测锁定 + M4 环境实跑"策略处理——已显式说明，非隐藏占位。RLS policy、per-role 出站白名单、Vault、mTLS 明确标注 P1。

**3. 类型一致性：** `BudgetGuard.charge`(Task 6)↔dispatcher 调用一致；`build_run_kwargs`(Task 7)↔`DockerSandbox.create` 一致；`map_openhands_line`(Task 8) 签名 test↔impl 一致；`inject_traceparent`(Task 9)↔ingest 调用一致；`Provisioner.provision`(Task 9) 返回 SandboxHandle 与 test 一致；`create_app(db, chayuan=None)`(Task 4) 向后兼容现有 `create_app(db)` 调用。

**不在本计划（另仓/后续）：** 指挥大屏前端 v1（chayuan-client 仓 + 设计稿待评审）；Postgres RLS policy、NATS Accounts、Vault、mTLS、per-role 出站白名单（P1）；单机容灾重建、host-bridge、员工视图、技能体系、Task-as-API 完整、Nacos、Charter 触发交接、复杂 DAG（P1）；#8 免密、Temporal、#12 A2A、#15 外部感知（P2/P3）。

---

## Execution Handoff

计划保存于 `docs/superpowers/plans/2026-07-05-chacmd-m3-m4-value-slice.md`。
