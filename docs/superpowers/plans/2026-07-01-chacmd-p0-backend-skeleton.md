# ChaCMD P0 Backend Skeleton (M1+M2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the ChaCMD thin real-time dispatch core so a容器 agent-bridge can reverse-connect, register by nickname (no IP), receive a dispatch, run an agent (fake in tests / OpenHands in prod), stream events back through the bus to persisted state, and drop产物 into a per-job volume — with all I1–I10 swap-point interfaces pre-defined from day one.

**Architecture:** A greenfield Python package `chacmd/` (Orchestrator + bridge-gateway + interface layer + FastAPI) plus an `agent-bridge/` package (子容器 resident service). All察元 dependencies go through the I1 `ChayuanClient` **HTTP** abstraction (fake in tests), so the core runs standalone. All addressing is logical (nickname / bus subject / volume path) — **no container IP anywhere**. State lives in a dialect-agnostic DB layer (SQLAlchemy 2.0 async; SQLite in tests, Postgres in prod). Events flow over an `EventBus` abstraction (in-memory in tests, NATS in prod).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, `websockets`, `nats-py` (default EventBus), `httpx` (I1 client), pytest + pytest-asyncio, `ruff`.

---

## Assumptions & Scope

**Repo placement (decision):** The Orchestrator/gateway code is developed as a standalone package `chacmd/` at the repo root of the current working repo (`/work/chatop-ai`). Because it depends on察元 **only via HTTP (I1)**, its placement is flexible (can later mirror into the察元 monorepo per design §3.6 or stay its own repo). The子容器 resident service is developed at `agent-bridge/` (later packaged into the chatop-ai KasmVNC image).

**In scope (M1+M2):** I1–I8, I10 interfaces (abstraction + one default impl + one swap-point test); Job/Task state machine incl. `pending_approval`; container registry (nickname→session, no IP); bridge-gateway reverse-WS termination; agent-bridge reverse-connect + lease heartbeat + dispatch + event adapter; @nickname dispatch → AgentAdapter → event stream → EventBus → persisted; per-job volume with atomic done-marker; FastAPI HTTP API + OpenAPI + `python -m chacmd.cli start`; `code` (Task-as-API #20) stored on Job.

**Out of scope (follow-on plans):** I9 frontend seam (React; needs UI brainstorm); M3 real rootless/gVisor sandbox hardening, iframe preview, approval UI, real token-budget kill, full OTel; M4 real OpenHands + real察元 + real Postgres/NATS integration soak; multi-tenant Accounts, Nacos, national-crypto impls (interfaces exist; impls are P1+).

**Interface principle (all tasks):** every I-interface ships as (a) a `Protocol`/ABC, (b) one default implementation, (c) a fake for tests, and (d) a test proving "swap impl without changing callers."

---

## File Structure

```
chacmd/
  pyproject.toml                         # package metadata, deps, pytest config
  chacmd/
    __init__.py
    cli.py                               # `python -m chacmd.cli start`
    config.py                            # env-driven Settings
    container.py                         # composition root: wires interface impls (DI)
    interfaces/
      __init__.py
      chayuan_client.py                  # I1: ChayuanClient Protocol + HttpChayuanClient + FakeChayuanClient
      db.py                              # I2: Database (engine/session, dialect-agnostic)
      crypto.py                          # I3: Crypto Protocol + StdCrypto
      registry.py                        # I4: ServiceRegistry + ConfigSource Protocols + InProcess impls
      eventbus.py                        # I6: EventBus Protocol + InMemoryEventBus + NatsEventBus
      transport.py                       # I10: Transport Protocol + LogicalAddress (no IP)
      agent_adapter.py                   # I5: AgentAdapter ABC + FakeAgentAdapter + OpenHandsAdapter
      sandbox.py                         # I7: Sandbox Protocol + FakeSandbox + RootlessDockerSandbox
      auth.py                            # I8: AuthProvider Protocol + ChayuanAuthProvider + FakeAuthProvider
    domain/
      __init__.py
      state.py                           # JobState/TaskState enums + transition table
      models.py                          # SQLAlchemy models: Job, Task, ContainerReg, AuditEvent
      events.py                          # Event dataclass (unified event envelope)
      repository.py                      # JobRepository, ContainerRepository (over I2)
    orchestrator/
      __init__.py
      registrar.py                       # container register + lease heartbeat + nickname resolve
      dispatcher.py                      # @nickname dispatch → AgentAdapter → events
      ingest.py                          # event ingest → EventBus + persist + state transitions
    gateway/
      __init__.py
      bridge_gateway.py                  # reverse-WS termination + auth + publish to bus
      protocol.py                        # WS message envelope (register/heartbeat/dispatch/event/result)
    api/
      __init__.py
      app.py                             # FastAPI app + routes + OpenAPI
      schemas.py                         # Pydantic DTOs
    workspace.py                         # per-job volume: path, mkdir, atomic done-marker
  tests/
    conftest.py
    test_*.py

agent-bridge/
  pyproject.toml
  agent_bridge/
    __init__.py
    main.py                              # reverse-connect + lease heartbeat + dispatch loop
    event_adapter.py                     # OpenHands JSONL / stream-json → unified Event
  tests/
    test_*.py
```

---

## Milestone M1 — Foundation, Interfaces (I1–I10), Reverse-Connect Registration ("1 container online")

### Task 1: Project scaffold

**Files:**
- Create: `chacmd/pyproject.toml`
- Create: `chacmd/chacmd/__init__.py`
- Create: `chacmd/tests/conftest.py`
- Create: `chacmd/tests/test_smoke.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_smoke.py`:
```python
import chacmd


def test_package_version_exposed():
    assert chacmd.__version__ == "0.0.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'chacmd'` (package not installed yet).

- [ ] **Step 3: Write minimal implementation**

`chacmd/pyproject.toml`:
```toml
[project]
name = "chacmd"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn>=0.32",
  "sqlalchemy>=2.0",
  "aiosqlite>=0.20",
  "asyncpg>=0.29",
  "pydantic>=2.9",
  "httpx>=0.27",
  "websockets>=13",
  "nats-py>=2.9",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24", "ruff>=0.7"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"
```

`chacmd/chacmd/__init__.py`:
```python
__version__ = "0.0.0"
```

`chacmd/tests/conftest.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && pip install -e ".[dev]" && python -m pytest tests/test_smoke.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chacmd/pyproject.toml chacmd/chacmd/__init__.py chacmd/tests/conftest.py chacmd/tests/test_smoke.py
git commit -m "chore(chacmd): scaffold package + smoke test"
```

---

### Task 2: I2 — Database access layer (dialect-agnostic)

**Files:**
- Create: `chacmd/chacmd/interfaces/db.py`
- Create: `chacmd/chacmd/interfaces/__init__.py`
- Test: `chacmd/tests/test_db.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_db.py`:
```python
import pytest
from sqlalchemy import text
from chacmd.interfaces.db import Database


@pytest.mark.asyncio
async def test_database_runs_query_on_any_dialect():
    db = Database(url="sqlite+aiosqlite:///:memory:")
    await db.create_all()
    async with db.session() as s:
        result = await s.execute(text("SELECT 1"))
        assert result.scalar() == 1
    await db.dispose()


def test_dialect_name_is_not_hardcoded():
    # I2 must expose the dialect so callers never assume postgres.
    db = Database(url="sqlite+aiosqlite:///:memory:")
    assert db.dialect == "sqlite"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: chacmd.interfaces.db`.

- [ ] **Step 3: Write minimal implementation**

`chacmd/chacmd/interfaces/__init__.py`:
```python
```

`chacmd/chacmd/interfaces/db.py`:
```python
from __future__ import annotations

from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ChaCMD models."""


class Database:
    """I2 — dialect-agnostic DB access. SQLite in tests, Postgres (or 达梦/金仓) in prod.

    Callers MUST go through session()/create_all() and never emit dialect-specific SQL.
    """

    def __init__(self, url: str) -> None:
        self._engine = create_async_engine(url, future=True)
        self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)

    @property
    def dialect(self) -> str:
        return self._engine.dialect.name

    async def create_all(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncSession:
        async with self._sessionmaker() as s:
            yield s

    async def dispose(self) -> None:
        await self._engine.dispose()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_db.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add chacmd/chacmd/interfaces/__init__.py chacmd/chacmd/interfaces/db.py chacmd/tests/test_db.py
git commit -m "feat(chacmd): I2 dialect-agnostic Database layer"
```

---

### Task 3: I3 — Crypto abstraction

**Files:**
- Create: `chacmd/chacmd/interfaces/crypto.py`
- Test: `chacmd/tests/test_crypto.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_crypto.py`:
```python
from chacmd.interfaces.crypto import Crypto, StdCrypto


def test_std_crypto_hmac_roundtrip():
    c: Crypto = StdCrypto(secret=b"k")
    sig = c.sign(b"payload")
    assert c.verify(b"payload", sig) is True
    assert c.verify(b"tampered", sig) is False


def test_std_crypto_hash_stable():
    c = StdCrypto(secret=b"k")
    assert c.hash(b"abc") == c.hash(b"abc")
    assert c.hash(b"abc") != c.hash(b"abd")


def test_crypto_is_swappable_protocol():
    # A different impl with the same Protocol must satisfy callers.
    class NullCrypto:
        def sign(self, data: bytes) -> bytes: return b"x"
        def verify(self, data: bytes, sig: bytes) -> bool: return sig == b"x"
        def hash(self, data: bytes) -> str: return "0"
        def encrypt(self, data: bytes) -> bytes: return data
        def decrypt(self, data: bytes) -> bytes: return data

    def use(c: Crypto) -> bool:
        return c.verify(b"p", c.sign(b"p"))

    assert use(NullCrypto()) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_crypto.py -v`
Expected: FAIL — `ModuleNotFoundError: chacmd.interfaces.crypto`.

- [ ] **Step 3: Write minimal implementation**

`chacmd/chacmd/interfaces/crypto.py`:
```python
from __future__ import annotations

import hashlib
import hmac
from typing import Protocol, runtime_checkable


@runtime_checkable
class Crypto(Protocol):
    """I3 — crypto abstraction. Default = std (HMAC/SHA/AES). Swap point = 国密 SM2/3/4."""

    def sign(self, data: bytes) -> bytes: ...
    def verify(self, data: bytes, sig: bytes) -> bool: ...
    def hash(self, data: bytes) -> str: ...
    def encrypt(self, data: bytes) -> bytes: ...
    def decrypt(self, data: bytes) -> bytes: ...


class StdCrypto:
    """Standard-algorithm default implementation."""

    def __init__(self, secret: bytes) -> None:
        self._secret = secret

    def sign(self, data: bytes) -> bytes:
        return hmac.new(self._secret, data, hashlib.sha256).digest()

    def verify(self, data: bytes, sig: bytes) -> bool:
        return hmac.compare_digest(self.sign(data), sig)

    def hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def encrypt(self, data: bytes) -> bytes:
        # P0 default: XOR-with-keystream placeholder is NOT acceptable; use a real cipher.
        # Minimal real AES-GCM via hashlib-scrypt-derived key would add a dep; for P0 the
        # encrypt/decrypt pair is identity-guarded behind the abstraction and only used by
        # the vault module (P1). Kept reversible + explicit for now.
        return data

    def decrypt(self, data: bytes) -> bytes:
        return data
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_crypto.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chacmd/chacmd/interfaces/crypto.py chacmd/tests/test_crypto.py
git commit -m "feat(chacmd): I3 Crypto abstraction + StdCrypto"
```

---

### Task 4: I10 — Transport / logical addressing (no IP)

**Files:**
- Create: `chacmd/chacmd/interfaces/transport.py`
- Test: `chacmd/tests/test_transport.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_transport.py`:
```python
import pytest
from chacmd.interfaces.transport import LogicalAddress, InProcessTransport


def test_logical_address_rejects_ip_like_targets():
    with pytest.raises(ValueError):
        LogicalAddress.nickname("10.0.0.5")  # looks like an IP → forbidden
    ok = LogicalAddress.nickname("radar-analyst")
    assert ok.kind == "nickname"
    assert ok.value == "radar-analyst"


def test_subject_and_volume_addresses():
    assert LogicalAddress.subject("agent.pm.inbox").value == "agent.pm.inbox"
    assert LogicalAddress.volume("job-123").value == "/workspace/job-123"


@pytest.mark.asyncio
async def test_inprocess_transport_delivers_by_logical_name_not_ip():
    t = InProcessTransport()
    received = []
    await t.bind(LogicalAddress.nickname("worker-1"), received.append)
    await t.send(LogicalAddress.nickname("worker-1"), {"hello": "world"})
    assert received == [{"hello": "world"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_transport.py -v`
Expected: FAIL — `ModuleNotFoundError: chacmd.interfaces.transport`.

- [ ] **Step 3: Write minimal implementation**

`chacmd/chacmd/interfaces/transport.py`:
```python
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol


def _looks_like_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class LogicalAddress:
    """Logical, IP-free address. kind ∈ {nickname, subject, volume, endpoint}."""

    kind: str
    value: str

    @staticmethod
    def nickname(name: str) -> "LogicalAddress":
        if _looks_like_ip(name):
            raise ValueError(f"nickname must not be an IP: {name}")
        return LogicalAddress("nickname", name)

    @staticmethod
    def subject(subj: str) -> "LogicalAddress":
        return LogicalAddress("subject", subj)

    @staticmethod
    def volume(job_id: str) -> "LogicalAddress":
        return LogicalAddress("volume", f"/workspace/{job_id}")

    @staticmethod
    def endpoint(service_name: str) -> "LogicalAddress":
        if _looks_like_ip(service_name):
            raise ValueError(f"endpoint must be a service name, not an IP: {service_name}")
        return LogicalAddress("endpoint", service_name)


Handler = Callable[[dict], Awaitable[None] | None]


class Transport(Protocol):
    """I10 — resolve logical name → channel, hiding IP. Swap: reverse-WS / bus / overlay-mesh."""

    async def bind(self, addr: LogicalAddress, handler: Handler) -> None: ...
    async def send(self, addr: LogicalAddress, message: dict) -> None: ...


class InProcessTransport:
    """Default test transport: pure in-process routing by logical name."""

    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str], Handler] = {}

    async def bind(self, addr: LogicalAddress, handler: Handler) -> None:
        self._handlers[(addr.kind, addr.value)] = handler

    async def send(self, addr: LogicalAddress, message: dict) -> None:
        handler = self._handlers.get((addr.kind, addr.value))
        if handler is None:
            raise KeyError(f"no bound handler for {addr}")
        result = handler(message)
        if result is not None:
            await result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_transport.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chacmd/chacmd/interfaces/transport.py chacmd/tests/test_transport.py
git commit -m "feat(chacmd): I10 Transport + LogicalAddress (no-IP addressing)"
```

---

### Task 5: I6 — EventBus abstraction

**Files:**
- Create: `chacmd/chacmd/interfaces/eventbus.py`
- Test: `chacmd/tests/test_eventbus.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_eventbus.py`:
```python
import asyncio
import pytest
from chacmd.interfaces.eventbus import EventBus, InMemoryEventBus


@pytest.mark.asyncio
async def test_inmemory_bus_publish_subscribe_by_subject():
    bus: EventBus = InMemoryEventBus()
    got = []

    async def consume():
        async for msg in bus.subscribe("job.j1.progress"):
            got.append(msg)
            if len(got) == 2:
                return

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)  # let subscriber attach
    await bus.publish("job.j1.progress", {"seq": 1})
    await bus.publish("job.j1.progress", {"seq": 2})
    await asyncio.wait_for(task, timeout=1)
    assert [m["seq"] for m in got] == [1, 2]


@pytest.mark.asyncio
async def test_subject_isolation():
    bus = InMemoryEventBus()
    got = []

    async def consume():
        async for msg in bus.subscribe("job.j1.progress"):
            got.append(msg)
            return

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)
    await bus.publish("job.OTHER.progress", {"seq": 9})  # different subject → ignored
    await bus.publish("job.j1.progress", {"seq": 1})
    await asyncio.wait_for(task, timeout=1)
    assert got == [{"seq": 1}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_eventbus.py -v`
Expected: FAIL — `ModuleNotFoundError: chacmd.interfaces.eventbus`.

- [ ] **Step 3: Write minimal implementation**

`chacmd/chacmd/interfaces/eventbus.py`:
```python
from __future__ import annotations

import asyncio
from typing import AsyncIterator, Protocol


class EventBus(Protocol):
    """I6 — event/progress/A2A transport. Default InMemory (tests) / NATS (prod).

    Subject scheme (no IP): job.<id>.<stage> / agent.<nickname>.inbox / heartbeat.<nickname>.
    """

    async def publish(self, subject: str, message: dict) -> None: ...
    def subscribe(self, subject: str) -> AsyncIterator[dict]: ...


class InMemoryEventBus:
    """Default in-process bus with exact-subject matching (P0/tests)."""

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue]] = {}

    async def publish(self, subject: str, message: dict) -> None:
        for q in self._queues.get(subject, []):
            await q.put(message)

    async def subscribe(self, subject: str) -> AsyncIterator[dict]:
        q: asyncio.Queue = asyncio.Queue()
        self._queues.setdefault(subject, []).append(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._queues[subject].remove(q)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_eventbus.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chacmd/chacmd/interfaces/eventbus.py chacmd/tests/test_eventbus.py
git commit -m "feat(chacmd): I6 EventBus abstraction + InMemoryEventBus"
```

---

### Task 6: I4 — ServiceRegistry + ConfigSource SPI

**Files:**
- Create: `chacmd/chacmd/interfaces/registry.py`
- Test: `chacmd/tests/test_registry.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_registry.py`:
```python
import pytest
from chacmd.interfaces.registry import (
    ServiceRegistry, ConfigSource, InProcessServiceRegistry, InProcessConfigSource, ServiceInstance,
)


@pytest.mark.asyncio
async def test_register_and_resolve_by_service_name_not_ip():
    reg: ServiceRegistry = InProcessServiceRegistry()
    await reg.register(ServiceInstance(name="chacmd-orchestrator", handle="session-abc", meta={"role": "core"}))
    found = await reg.resolve("chacmd-orchestrator")
    assert found[0].handle == "session-abc"
    assert "ip" not in found[0].meta  # handle is a logical session, never an IP


@pytest.mark.asyncio
async def test_deregister_removes_instance():
    reg = InProcessServiceRegistry()
    await reg.register(ServiceInstance(name="svc", handle="h1", meta={}))
    await reg.deregister("svc", "h1")
    assert await reg.resolve("svc") == []


def test_config_source_get_default():
    cfg: ConfigSource = InProcessConfigSource({"chayuan.base_url": "http://127.0.0.1:8000"})
    assert cfg.get("chayuan.base_url") == "http://127.0.0.1:8000"
    assert cfg.get("missing", "fallback") == "fallback"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: chacmd.interfaces.registry`.

- [ ] **Step 3: Write minimal implementation**

`chacmd/chacmd/interfaces/registry.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ServiceInstance:
    name: str
    handle: str  # logical handle (reverse-WS session id / bus subject) — NEVER an IP
    meta: dict[str, Any] = field(default_factory=dict)


class ServiceRegistry(Protocol):
    """I4 — service registration/discovery. Default InProcess / swap Nacos, Consul, etcd.

    Registered handles are logical (session/subject), enabling OpenFeign-by-service-name (§6.23).
    """

    async def register(self, instance: ServiceInstance) -> None: ...
    async def deregister(self, name: str, handle: str) -> None: ...
    async def resolve(self, name: str) -> list[ServiceInstance]: ...


class ConfigSource(Protocol):
    """I4 — config source. Default InProcess/env / swap Nacos config center."""

    def get(self, key: str, default: Any = None) -> Any: ...


class InProcessServiceRegistry:
    def __init__(self) -> None:
        self._by_name: dict[str, list[ServiceInstance]] = {}

    async def register(self, instance: ServiceInstance) -> None:
        instances = self._by_name.setdefault(instance.name, [])
        instances[:] = [i for i in instances if i.handle != instance.handle]
        instances.append(instance)

    async def deregister(self, name: str, handle: str) -> None:
        self._by_name[name] = [i for i in self._by_name.get(name, []) if i.handle != handle]

    async def resolve(self, name: str) -> list[ServiceInstance]:
        return list(self._by_name.get(name, []))


class InProcessConfigSource:
    def __init__(self, values: dict[str, Any]) -> None:
        self._values = dict(values)

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_registry.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chacmd/chacmd/interfaces/registry.py chacmd/tests/test_registry.py
git commit -m "feat(chacmd): I4 ServiceRegistry + ConfigSource SPI (InProcess default)"
```

---

### Task 7: I1 — ChayuanClient (HTTP abstraction + fake)

**Files:**
- Create: `chacmd/chacmd/interfaces/chayuan_client.py`
- Test: `chacmd/tests/test_chayuan_client.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_chayuan_client.py`:
```python
import pytest
from chacmd.interfaces.chayuan_client import ChayuanClient, FakeChayuanClient


@pytest.mark.asyncio
async def test_fake_chayuan_client_authz_and_weburl():
    c: ChayuanClient = FakeChayuanClient(web_url="http://chayuan.local")
    assert await c.authorize(subject="u1", resource="container:pm", action="dispatch") is True
    c.deny("u1", "container:secret", "dispatch")
    assert await c.authorize(subject="u1", resource="container:secret", action="dispatch") is False
    assert c.web_url() == "http://chayuan.local"


@pytest.mark.asyncio
async def test_fake_chayuan_client_chat_records_calls():
    c = FakeChayuanClient()
    out = await c.chat_completions(model="deepseek", messages=[{"role": "user", "content": "hi"}])
    assert out["choices"][0]["message"]["content"]  # non-empty stub reply
    assert c.calls[-1]["model"] == "deepseek"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_chayuan_client.py -v`
Expected: FAIL — `ModuleNotFoundError: chacmd.interfaces.chayuan_client`.

- [ ] **Step 3: Write minimal implementation**

`chacmd/chacmd/interfaces/chayuan_client.py`:
```python
from __future__ import annotations

from typing import Any, Protocol

import httpx


class ChayuanClient(Protocol):
    """I1 — ALL 察元 dependencies via HTTP. Default Http (localhost=形态B / remote=形态C).

    Because it is HTTP, ChaCMD never needs 察元 in-process; enables 轻量挂载 (§3.9).
    """

    async def chat_completions(self, model: str, messages: list[dict], **kw: Any) -> dict: ...
    async def kb_query(self, ku_ids: list[str], query: str, **kw: Any) -> dict: ...
    async def authorize(self, subject: str, resource: str, action: str) -> bool: ...
    async def whoami(self, token: str) -> dict: ...
    def web_url(self) -> str: ...


class HttpChayuanClient:
    """Default: talk to a deployed 察元 over HTTP (localhost or remote)."""

    def __init__(self, base_url: str, web_url: str, *, timeout: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._web = web_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self._base, timeout=timeout)

    async def chat_completions(self, model: str, messages: list[dict], **kw: Any) -> dict:
        resp = await self._client.post("/v1/chat/completions", json={"model": model, "messages": messages, **kw})
        resp.raise_for_status()
        return resp.json()

    async def kb_query(self, ku_ids: list[str], query: str, **kw: Any) -> dict:
        resp = await self._client.post("/api/v1/kb-query/search", json={"ku_ids": ku_ids, "query": query, **kw})
        resp.raise_for_status()
        return resp.json()

    async def authorize(self, subject: str, resource: str, action: str) -> bool:
        resp = await self._client.post(
            "/api/v1/authz/check", json={"subject": subject, "resource": resource, "action": action}
        )
        resp.raise_for_status()
        return bool(resp.json().get("allowed", False))

    async def whoami(self, token: str) -> dict:
        resp = await self._client.get("/api/v1/whoami", headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        return resp.json()

    def web_url(self) -> str:
        return self._web

    async def aclose(self) -> None:
        await self._client.aclose()


class FakeChayuanClient:
    """Test double: no network. Records calls, allow-by-default authz."""

    def __init__(self, web_url: str = "http://chayuan.test") -> None:
        self._web = web_url
        self._denied: set[tuple[str, str, str]] = set()
        self.calls: list[dict] = []

    def deny(self, subject: str, resource: str, action: str) -> None:
        self._denied.add((subject, resource, action))

    async def chat_completions(self, model: str, messages: list[dict], **kw: Any) -> dict:
        self.calls.append({"model": model, "messages": messages, **kw})
        return {"choices": [{"message": {"role": "assistant", "content": "[fake reply]"}}]}

    async def kb_query(self, ku_ids: list[str], query: str, **kw: Any) -> dict:
        self.calls.append({"kb": ku_ids, "query": query})
        return {"hits": []}

    async def authorize(self, subject: str, resource: str, action: str) -> bool:
        return (subject, resource, action) not in self._denied

    async def whoami(self, token: str) -> dict:
        return {"subject": "test-user", "dept": "test-dept"}

    def web_url(self) -> str:
        return self._web
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_chayuan_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chacmd/chacmd/interfaces/chayuan_client.py chacmd/tests/test_chayuan_client.py
git commit -m "feat(chacmd): I1 ChayuanClient HTTP abstraction + fake"
```

---

### Task 8: I8 — AuthProvider

**Files:**
- Create: `chacmd/chacmd/interfaces/auth.py`
- Test: `chacmd/tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_auth.py`:
```python
import pytest
from chacmd.interfaces.auth import AuthProvider, FakeAuthProvider


@pytest.mark.asyncio
async def test_fake_auth_issue_and_verify():
    a: AuthProvider = FakeAuthProvider()
    token = await a.issue_token(subject="u1", dept="d1")
    claims = await a.verify(token)
    assert claims["subject"] == "u1"
    assert claims["dept"] == "d1"


@pytest.mark.asyncio
async def test_fake_auth_rejects_bad_token():
    a = FakeAuthProvider()
    with pytest.raises(ValueError):
        await a.verify("not-a-real-token")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: chacmd.interfaces.auth`.

- [ ] **Step 3: Write minimal implementation**

`chacmd/chacmd/interfaces/auth.py`:
```python
from __future__ import annotations

import json
import uuid
from typing import Any, Protocol


class AuthProvider(Protocol):
    """I8 — identity/auth. Default 察元-internal (via I1) / swap OIDC/LDAP/SSO + 一次性token(形态C) + 三员."""

    async def issue_token(self, subject: str, dept: str) -> str: ...
    async def verify(self, token: str) -> dict[str, Any]: ...


class FakeAuthProvider:
    """Test double: opaque token → in-memory claim store."""

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}

    async def issue_token(self, subject: str, dept: str) -> str:
        token = uuid.uuid5(uuid.NAMESPACE_OID, f"{subject}:{dept}").hex
        self._store[token] = {"subject": subject, "dept": dept}
        return token

    async def verify(self, token: str) -> dict[str, Any]:
        if token not in self._store:
            raise ValueError("invalid token")
        return dict(self._store[token])


class ChayuanAuthProvider:
    """Default prod impl: delegate to 察元 whoami via I1 (imported lazily to avoid cycles)."""

    def __init__(self, chayuan_client: Any) -> None:
        self._c = chayuan_client

    async def issue_token(self, subject: str, dept: str) -> str:
        # P0: 察元 issues tokens; ChaCMD does not mint its own. Placeholder passes through dept-scoped id.
        return json.dumps({"subject": subject, "dept": dept})

    async def verify(self, token: str) -> dict[str, Any]:
        return await self._c.whoami(token)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_auth.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chacmd/chacmd/interfaces/auth.py chacmd/tests/test_auth.py
git commit -m "feat(chacmd): I8 AuthProvider (fake + 察元-delegating default)"
```

---

### Task 9: I5 — AgentAdapter ABC (+ FakeAgentAdapter)

**Files:**
- Create: `chacmd/chacmd/domain/events.py`
- Create: `chacmd/chacmd/domain/__init__.py`
- Create: `chacmd/chacmd/interfaces/agent_adapter.py`
- Test: `chacmd/tests/test_agent_adapter.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_agent_adapter.py`:
```python
import pytest
from chacmd.domain.events import Event
from chacmd.interfaces.agent_adapter import AgentAdapter, FakeAgentAdapter, DispatchSpec


@pytest.mark.asyncio
async def test_fake_adapter_streams_events_then_result():
    a: AgentAdapter = FakeAgentAdapter(steps=["step-1", "step-2"])
    spec = DispatchSpec(job_id="j1", task_id="t1", nickname="dev", goal="build app", system_prompt="you are dev")
    events = [e async for e in a.dispatch(spec)]
    kinds = [e.kind for e in events]
    assert kinds == ["started", "progress", "progress", "succeeded"]
    assert all(isinstance(e, Event) for e in events)
    assert events[-1].payload["result"] == "ok"


def test_adapter_manifest_declares_capabilities():
    a = FakeAgentAdapter(steps=[])
    assert a.manifest()["name"] == "fake"
    assert "stream" in a.manifest()["capabilities"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_agent_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: chacmd.domain.events`.

- [ ] **Step 3: Write minimal implementation**

`chacmd/chacmd/domain/__init__.py`:
```python
```

`chacmd/chacmd/domain/events.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Event:
    """Unified event envelope streamed from any agent through the bus (§6.6)."""

    job_id: str
    task_id: str
    container: str          # nickname (logical, no IP)
    kind: str               # started | progress | pending_approval | succeeded | failed | interrupted
    seq: int
    payload: dict[str, Any] = field(default_factory=dict)

    def subject(self) -> str:
        return f"job.{self.job_id}.{self.kind}"
```

`chacmd/chacmd/interfaces/agent_adapter.py`:
```python
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, AsyncIterator

from chacmd.domain.events import Event


@dataclass
class DispatchSpec:
    job_id: str
    task_id: str
    nickname: str
    goal: str
    system_prompt: str
    inputs: dict[str, Any] | None = None


class AgentAdapter(abc.ABC):
    """I5 — pluggable agent runtime. Default OpenHands / swap Codex, Hermes, OpenClaw, Claude Code.

    Written as an ABC so a new agent is drop-in (no `if system_id` in core).
    """

    @abc.abstractmethod
    def dispatch(self, spec: DispatchSpec) -> AsyncIterator[Event]: ...

    @abc.abstractmethod
    async def health(self) -> bool: ...

    @abc.abstractmethod
    async def cancel(self, job_id: str, task_id: str) -> None: ...

    @abc.abstractmethod
    def manifest(self) -> dict[str, Any]: ...


class FakeAgentAdapter(AgentAdapter):
    """Test double: deterministic event stream, no external process."""

    def __init__(self, steps: list[str]) -> None:
        self._steps = steps
        self._cancelled: set[tuple[str, str]] = set()

    async def dispatch(self, spec: DispatchSpec) -> AsyncIterator[Event]:
        seq = 0
        yield Event(spec.job_id, spec.task_id, spec.nickname, "started", seq, {"goal": spec.goal})
        for step in self._steps:
            if (spec.job_id, spec.task_id) in self._cancelled:
                seq += 1
                yield Event(spec.job_id, spec.task_id, spec.nickname, "interrupted", seq, {"at": step})
                return
            seq += 1
            yield Event(spec.job_id, spec.task_id, spec.nickname, "progress", seq, {"step": step})
        seq += 1
        yield Event(spec.job_id, spec.task_id, spec.nickname, "succeeded", seq, {"result": "ok"})

    async def health(self) -> bool:
        return True

    async def cancel(self, job_id: str, task_id: str) -> None:
        self._cancelled.add((job_id, task_id))

    def manifest(self) -> dict[str, Any]:
        return {"name": "fake", "capabilities": ["stream", "cancel"]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_agent_adapter.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chacmd/chacmd/domain/__init__.py chacmd/chacmd/domain/events.py chacmd/chacmd/interfaces/agent_adapter.py chacmd/tests/test_agent_adapter.py
git commit -m "feat(chacmd): I5 AgentAdapter ABC + Event envelope + FakeAgentAdapter"
```

---

### Task 10: I7 — Sandbox provider

**Files:**
- Create: `chacmd/chacmd/interfaces/sandbox.py`
- Test: `chacmd/tests/test_sandbox.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_sandbox.py`:
```python
import pytest
from chacmd.interfaces.sandbox import Sandbox, FakeSandbox, SandboxSpec


@pytest.mark.asyncio
async def test_fake_sandbox_create_and_destroy():
    s: Sandbox = FakeSandbox()
    handle = await s.create(SandboxSpec(nickname="dev", image="chatop-base"))
    assert handle.nickname == "dev"
    assert handle.id in s.live
    await s.destroy(handle.id)
    assert handle.id not in s.live


def test_sandbox_spec_forbids_docker_socket_mount():
    # Hard security rule (§10.4-S1 / R4): socket must never be mounted into the sandbox.
    with pytest.raises(ValueError):
        SandboxSpec(nickname="x", image="i", mounts=["/var/run/docker.sock:/var/run/docker.sock"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_sandbox.py -v`
Expected: FAIL — `ModuleNotFoundError: chacmd.interfaces.sandbox`.

- [ ] **Step 3: Write minimal implementation**

`chacmd/chacmd/interfaces/sandbox.py`:
```python
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class SandboxSpec:
    nickname: str
    image: str
    mounts: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for m in self.mounts:
            if "docker.sock" in m:
                raise ValueError("docker socket must never be mounted into a sandbox (R4)")


@dataclass
class SandboxHandle:
    id: str
    nickname: str


class Sandbox(Protocol):
    """I7 — isolation runtime. Default rootless Docker / swap gVisor, Kata, 国产安全容器."""

    async def create(self, spec: SandboxSpec) -> SandboxHandle: ...
    async def destroy(self, handle_id: str) -> None: ...


class FakeSandbox:
    """Test double: track live handles, no real containers."""

    def __init__(self) -> None:
        self.live: dict[str, SandboxHandle] = {}

    async def create(self, spec: SandboxSpec) -> SandboxHandle:
        handle = SandboxHandle(id=uuid.uuid4().hex, nickname=spec.nickname)
        self.live[handle.id] = handle
        return handle

    async def destroy(self, handle_id: str) -> None:
        self.live.pop(handle_id, None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_sandbox.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chacmd/chacmd/interfaces/sandbox.py chacmd/tests/test_sandbox.py
git commit -m "feat(chacmd): I7 Sandbox provider (fake + socket-mount guard)"
```

---

### Task 11: Job/Task state machine (incl. pending_approval)

**Files:**
- Create: `chacmd/chacmd/domain/state.py`
- Test: `chacmd/tests/test_state.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_state.py`:
```python
import pytest
from chacmd.domain.state import JobState, can_transition, transition


def test_happy_path_transitions():
    assert can_transition(JobState.QUEUED, JobState.DISPATCHING)
    assert can_transition(JobState.DISPATCHING, JobState.RUNNING)
    assert can_transition(JobState.RUNNING, JobState.SUCCEEDED)


def test_approval_loop():
    assert can_transition(JobState.RUNNING, JobState.PENDING_APPROVAL)
    assert can_transition(JobState.PENDING_APPROVAL, JobState.RUNNING)      # approved
    assert can_transition(JobState.PENDING_APPROVAL, JobState.CANCELLED)    # rejected→cancel


def test_interrupted_from_running():
    assert can_transition(JobState.RUNNING, JobState.INTERRUPTED)


def test_illegal_transition_raises():
    with pytest.raises(ValueError):
        transition(JobState.SUCCEEDED, JobState.RUNNING)  # terminal → nothing
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_state.py -v`
Expected: FAIL — `ModuleNotFoundError: chacmd.domain.state`.

- [ ] **Step 3: Write minimal implementation**

`chacmd/chacmd/domain/state.py`:
```python
from __future__ import annotations

from enum import Enum


class JobState(str, Enum):
    QUEUED = "queued"
    DISPATCHING = "dispatching"
    RUNNING = "running"
    PENDING_APPROVAL = "pending_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


# TaskState mirrors JobState for P0 (single-task jobs); kept as an alias for clarity.
TaskState = JobState

_ALLOWED: dict[JobState, set[JobState]] = {
    JobState.QUEUED: {JobState.DISPATCHING, JobState.CANCELLED},
    JobState.DISPATCHING: {JobState.RUNNING, JobState.FAILED, JobState.INTERRUPTED},
    JobState.RUNNING: {
        JobState.PENDING_APPROVAL,
        JobState.SUCCEEDED,
        JobState.FAILED,
        JobState.INTERRUPTED,
        JobState.CANCELLED,
    },
    JobState.PENDING_APPROVAL: {JobState.RUNNING, JobState.CANCELLED, JobState.FAILED},
    JobState.SUCCEEDED: set(),
    JobState.FAILED: set(),
    JobState.INTERRUPTED: set(),
    JobState.CANCELLED: set(),
}


def can_transition(src: JobState, dst: JobState) -> bool:
    return dst in _ALLOWED[src]


def transition(src: JobState, dst: JobState) -> JobState:
    if not can_transition(src, dst):
        raise ValueError(f"illegal transition {src} -> {dst}")
    return dst
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_state.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chacmd/chacmd/domain/state.py chacmd/tests/test_state.py
git commit -m "feat(chacmd): Job/Task state machine with pending_approval"
```

---

### Task 12: Domain models + repositories (over I2)

**Files:**
- Create: `chacmd/chacmd/domain/models.py`
- Create: `chacmd/chacmd/domain/repository.py`
- Test: `chacmd/tests/test_repository.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_repository.py`:
```python
import pytest
from chacmd.interfaces.db import Database
from chacmd.domain.state import JobState
from chacmd.domain.repository import JobRepository, ContainerRepository


@pytest.fixture
async def db():
    d = Database(url="sqlite+aiosqlite:///:memory:")
    await d.create_all()
    yield d
    await d.dispose()


@pytest.mark.asyncio
async def test_create_and_get_job(db):
    repo = JobRepository(db)
    job = await repo.create(code="world-rank-app", goal="build ranking app", dept="d1")
    assert job.state == JobState.QUEUED.value
    fetched = await repo.get(job.id)
    assert fetched.code == "world-rank-app"
    assert fetched.dept == "d1"


@pytest.mark.asyncio
async def test_set_state_persists(db):
    repo = JobRepository(db)
    job = await repo.create(code="c", goal="g", dept="d1")
    await repo.set_state(job.id, JobState.DISPATCHING)
    assert (await repo.get(job.id)).state == JobState.DISPATCHING.value


@pytest.mark.asyncio
async def test_container_register_resolve_by_nickname(db):
    creg = ContainerRepository(db)
    await creg.upsert(nickname="dev", session="s1", dept="d1")
    row = await creg.resolve("dev")
    assert row.session == "s1"
    assert not hasattr(row, "ip")  # model has no ip column at all
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: chacmd.domain.models`.

- [ ] **Step 3: Write minimal implementation**

`chacmd/chacmd/domain/models.py`:
```python
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from chacmd.interfaces.db import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    code: Mapped[str] = mapped_column(String(128), index=True)          # #20 Task-as-API contract id
    goal: Mapped[str] = mapped_column(String)
    dept: Mapped[str] = mapped_column(String(64), index=True)          # tenant = dept (RLS key, NFR-T1)
    state: Mapped[str] = mapped_column(String(32), default="queued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(32), index=True)
    nickname: Mapped[str] = mapped_column(String(128))                 # logical, no IP
    state: Mapped[str] = mapped_column(String(32), default="queued")


class ContainerReg(Base):
    __tablename__ = "container_reg"

    nickname: Mapped[str] = mapped_column(String(128), primary_key=True)  # logical id
    session: Mapped[str] = mapped_column(String(128))                     # reverse-WS session handle (NOT ip)
    dept: Mapped[str] = mapped_column(String(64), index=True)
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(32), index=True)
    task_id: Mapped[str] = mapped_column(String(32))
    container: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32))
    seq: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
```

`chacmd/chacmd/domain/repository.py`:
```python
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from chacmd.interfaces.db import Database
from chacmd.domain.models import Job, ContainerReg, AuditEvent
from chacmd.domain.state import JobState, transition
from chacmd.domain.events import Event


class JobRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, code: str, goal: str, dept: str) -> Job:
        async with self._db.session() as s:
            job = Job(code=code, goal=goal, dept=dept, state=JobState.QUEUED.value)
            s.add(job)
            await s.commit()
            await s.refresh(job)
            return job

    async def get(self, job_id: str) -> Job | None:
        async with self._db.session() as s:
            return await s.get(Job, job_id)

    async def set_state(self, job_id: str, dst: JobState) -> None:
        async with self._db.session() as s:
            job = await s.get(Job, job_id)
            job.state = transition(JobState(job.state), dst).value
            await s.commit()


class ContainerRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def upsert(self, nickname: str, session: str, dept: str) -> None:
        async with self._db.session() as s:
            row = await s.get(ContainerReg, nickname)
            if row is None:
                s.add(ContainerReg(nickname=nickname, session=session, dept=dept))
            else:
                row.session = session
                row.dept = dept
                row.last_heartbeat = datetime.now(timezone.utc)
            await s.commit()

    async def resolve(self, nickname: str) -> ContainerReg | None:
        async with self._db.session() as s:
            return await s.get(ContainerReg, nickname)

    async def touch(self, nickname: str) -> None:
        async with self._db.session() as s:
            row = await s.get(ContainerReg, nickname)
            if row:
                row.last_heartbeat = datetime.now(timezone.utc)
                await s.commit()


class AuditRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def append(self, e: Event) -> None:
        async with self._db.session() as s:
            s.add(AuditEvent(
                job_id=e.job_id, task_id=e.task_id, container=e.container,
                kind=e.kind, seq=e.seq, payload=e.payload,
            ))
            await s.commit()

    async def list_for_job(self, job_id: str) -> list[AuditEvent]:
        async with self._db.session() as s:
            rows = await s.execute(
                select(AuditEvent).where(AuditEvent.job_id == job_id).order_by(AuditEvent.seq)
            )
            return list(rows.scalars())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_repository.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chacmd/chacmd/domain/models.py chacmd/chacmd/domain/repository.py chacmd/tests/test_repository.py
git commit -m "feat(chacmd): domain models + repositories (dept tenant, no-IP registry, audit)"
```

---

### Task 13: WS protocol envelope + bridge-gateway registration

**Files:**
- Create: `chacmd/chacmd/gateway/__init__.py`
- Create: `chacmd/chacmd/gateway/protocol.py`
- Create: `chacmd/chacmd/orchestrator/__init__.py`
- Create: `chacmd/chacmd/orchestrator/registrar.py`
- Test: `chacmd/tests/test_registrar.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_registrar.py`:
```python
import pytest
from chacmd.interfaces.db import Database
from chacmd.domain.repository import ContainerRepository
from chacmd.gateway.protocol import Envelope
from chacmd.orchestrator.registrar import Registrar


@pytest.fixture
async def db():
    d = Database(url="sqlite+aiosqlite:///:memory:")
    await d.create_all()
    yield d
    await d.dispose()


@pytest.mark.asyncio
async def test_register_message_records_nickname_session(db):
    reg = Registrar(ContainerRepository(db))
    env = Envelope(type="register", nickname="dev", dept="d1", data={})
    await reg.handle(env, session="sess-1")
    row = await ContainerRepository(db).resolve("dev")
    assert row.session == "sess-1"


@pytest.mark.asyncio
async def test_heartbeat_updates_lease(db):
    reg = Registrar(ContainerRepository(db))
    await reg.handle(Envelope(type="register", nickname="dev", dept="d1", data={}), session="s1")
    before = (await ContainerRepository(db).resolve("dev")).last_heartbeat
    await reg.handle(Envelope(type="heartbeat", nickname="dev", dept="d1", data={}), session="s1")
    after = (await ContainerRepository(db).resolve("dev")).last_heartbeat
    assert after >= before


def test_envelope_rejects_unknown_type():
    with pytest.raises(ValueError):
        Envelope(type="bogus", nickname="x", dept="d", data={})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_registrar.py -v`
Expected: FAIL — `ModuleNotFoundError: chacmd.gateway.protocol`.

- [ ] **Step 3: Write minimal implementation**

`chacmd/chacmd/gateway/__init__.py`:
```python
```

`chacmd/chacmd/gateway/protocol.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Reverse-WS message types (container→gateway and gateway→container).
VALID_TYPES = {"register", "heartbeat", "dispatch", "event", "result", "cancel"}


@dataclass
class Envelope:
    type: str
    nickname: str          # logical id (no IP)
    dept: str
    data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in VALID_TYPES:
            raise ValueError(f"unknown envelope type: {self.type}")

    def to_json(self) -> dict:
        return {"type": self.type, "nickname": self.nickname, "dept": self.dept, "data": self.data}

    @staticmethod
    def from_json(d: dict) -> "Envelope":
        return Envelope(type=d["type"], nickname=d["nickname"], dept=d["dept"], data=d.get("data", {}))
```

`chacmd/chacmd/orchestrator/__init__.py`:
```python
```

`chacmd/chacmd/orchestrator/registrar.py`:
```python
from __future__ import annotations

from chacmd.domain.repository import ContainerRepository
from chacmd.gateway.protocol import Envelope


class Registrar:
    """Handles register/heartbeat envelopes → container registry (nickname→session, no IP)."""

    def __init__(self, containers: ContainerRepository) -> None:
        self._containers = containers

    async def handle(self, env: Envelope, session: str) -> None:
        if env.type == "register":
            await self._containers.upsert(nickname=env.nickname, session=session, dept=env.dept)
        elif env.type == "heartbeat":
            await self._containers.touch(env.nickname)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_registrar.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chacmd/chacmd/gateway/__init__.py chacmd/chacmd/gateway/protocol.py chacmd/chacmd/orchestrator/__init__.py chacmd/chacmd/orchestrator/registrar.py chacmd/tests/test_registrar.py
git commit -m "feat(chacmd): WS envelope + registrar (nickname→session, no IP)"
```

---

### Task 14: Lease-based liveness (judge-dead independent of bus)

**Files:**
- Create: `chacmd/chacmd/orchestrator/lease.py`
- Test: `chacmd/tests/test_lease.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_lease.py`:
```python
import pytest
from datetime import datetime, timezone, timedelta
from chacmd.interfaces.db import Database
from chacmd.domain.models import ContainerReg
from chacmd.domain.repository import ContainerRepository
from chacmd.orchestrator.lease import LeaseMonitor


@pytest.fixture
async def db():
    d = Database(url="sqlite+aiosqlite:///:memory:")
    await d.create_all()
    yield d
    await d.dispose()


@pytest.mark.asyncio
async def test_dead_containers_detected_by_stale_lease(db):
    creg = ContainerRepository(db)
    await creg.upsert(nickname="dev", session="s1", dept="d1")
    # Force stale heartbeat.
    async with db.session() as s:
        row = await s.get(ContainerReg, "dev")
        row.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=60)
        await s.commit()
    monitor = LeaseMonitor(creg, ttl_seconds=30)
    dead = await monitor.dead_nicknames()
    assert dead == ["dev"]


@pytest.mark.asyncio
async def test_fresh_container_not_dead(db):
    creg = ContainerRepository(db)
    await creg.upsert(nickname="dev", session="s1", dept="d1")
    monitor = LeaseMonitor(creg, ttl_seconds=30)
    assert await monitor.dead_nicknames() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_lease.py -v`
Expected: FAIL — `ModuleNotFoundError: chacmd.orchestrator.lease`.

- [ ] **Step 3: Write minimal implementation**

`chacmd/chacmd/orchestrator/lease.py`:
```python
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from sqlalchemy import select

from chacmd.domain.models import ContainerReg
from chacmd.domain.repository import ContainerRepository


class LeaseMonitor:
    """Judge-dead via independent lease (NOT via 'any heartbeat on the bus') — §10.1-C3."""

    def __init__(self, containers: ContainerRepository, ttl_seconds: int = 30) -> None:
        self._containers = containers
        self._ttl = ttl_seconds

    async def dead_nicknames(self) -> list[str]:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._ttl)
        async with self._containers._db.session() as s:  # noqa: SLF001 (repo shares db)
            rows = await s.execute(select(ContainerReg))
            dead = []
            for row in rows.scalars():
                hb = row.last_heartbeat
                if hb.tzinfo is None:
                    hb = hb.replace(tzinfo=timezone.utc)
                if hb < cutoff:
                    dead.append(row.nickname)
            return dead
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_lease.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chacmd/chacmd/orchestrator/lease.py chacmd/tests/test_lease.py
git commit -m "feat(chacmd): lease-based liveness (dead-judge decoupled from bus)"
```

---

### Task 15: bridge-gateway (reverse-WS termination + auth + registrar wiring)

**Files:**
- Create: `chacmd/chacmd/gateway/bridge_gateway.py`
- Test: `chacmd/tests/test_bridge_gateway.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_bridge_gateway.py`:
```python
import asyncio
import json
import pytest
import websockets
from chacmd.interfaces.db import Database
from chacmd.domain.repository import ContainerRepository
from chacmd.gateway.bridge_gateway import BridgeGateway


@pytest.fixture
async def db():
    d = Database(url="sqlite+aiosqlite:///:memory:")
    await d.create_all()
    yield d
    await d.dispose()


@pytest.mark.asyncio
async def test_container_reverse_connects_and_registers(db):
    gw = BridgeGateway(ContainerRepository(db), host="127.0.0.1", port=8767)
    await gw.start()
    try:
        async with websockets.connect("ws://127.0.0.1:8767/bridge") as ws:
            await ws.send(json.dumps({"type": "register", "nickname": "dev", "dept": "d1", "data": {}}))
            await asyncio.sleep(0.1)
            row = await ContainerRepository(db).resolve("dev")
            assert row is not None and row.session  # session recorded, no IP used
    finally:
        await gw.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_bridge_gateway.py -v`
Expected: FAIL — `ModuleNotFoundError: chacmd.gateway.bridge_gateway`.

- [ ] **Step 3: Write minimal implementation**

`chacmd/chacmd/gateway/bridge_gateway.py`:
```python
from __future__ import annotations

import json
import uuid
from typing import Awaitable, Callable

import websockets

from chacmd.domain.repository import ContainerRepository
from chacmd.gateway.protocol import Envelope
from chacmd.orchestrator.registrar import Registrar


class BridgeGateway:
    """Stateless connection tier: terminates reverse-WS, registers nickname→session, no IP.

    Sessions are logical ids; the gateway holds nickname→ws so the core can send by nickname.
    """

    def __init__(self, containers: ContainerRepository, host: str = "0.0.0.0", port: int = 8767) -> None:
        self._registrar = Registrar(containers)
        self._host = host
        self._port = port
        self._server: websockets.WebSocketServer | None = None
        self._sessions: dict[str, websockets.WebSocketServerProtocol] = {}   # nickname → ws
        self._event_sink: Callable[[Envelope], Awaitable[None]] | None = None

    def on_event(self, sink: Callable[[Envelope], Awaitable[None]]) -> None:
        self._event_sink = sink

    async def send_to(self, nickname: str, env: Envelope) -> None:
        ws = self._sessions.get(nickname)
        if ws is None:
            raise KeyError(f"no live session for nickname {nickname}")
        await ws.send(json.dumps(env.to_json()))

    async def _handle(self, ws: websockets.WebSocketServerProtocol) -> None:
        session = uuid.uuid4().hex
        try:
            async for raw in ws:
                env = Envelope.from_json(json.loads(raw))
                if env.type in ("register", "heartbeat"):
                    if env.type == "register":
                        self._sessions[env.nickname] = ws
                    await self._registrar.handle(env, session=session)
                elif env.type in ("event", "result") and self._event_sink:
                    await self._event_sink(env)
        finally:
            for nick, sock in list(self._sessions.items()):
                if sock is ws:
                    del self._sessions[nick]

    async def start(self) -> None:
        self._server = await websockets.serve(self._handle, self._host, self._port, subprotocols=None)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_bridge_gateway.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chacmd/chacmd/gateway/bridge_gateway.py chacmd/tests/test_bridge_gateway.py
git commit -m "feat(chacmd): bridge-gateway reverse-WS termination + registration"
```

---

## Milestone M2 — Dispatch, Execution, Event Stream, Volume, API

### Task 16: per-job volume (atomic done-marker)

**Files:**
- Create: `chacmd/chacmd/workspace.py`
- Test: `chacmd/tests/test_workspace.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_workspace.py`:
```python
import pytest
from pathlib import Path
from chacmd.workspace import Workspace


def test_job_dir_uses_code_and_is_isolated(tmp_path):
    ws = Workspace(root=tmp_path)
    d = ws.ensure_job_dir(job_id="j1", code="world-rank-app")
    assert d.exists()
    assert d.name == "world-rank-app"
    assert (tmp_path / "world-rank-app").exists()


def test_done_marker_is_atomic(tmp_path):
    ws = Workspace(root=tmp_path)
    ws.ensure_job_dir(job_id="j1", code="c")
    assert ws.is_done("j1", "c") is False
    ws.mark_done("j1", "c", {"artifact": "out.zip"})
    assert ws.is_done("j1", "c") is True
    assert ws.read_done("j1", "c")["artifact"] == "out.zip"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_workspace.py -v`
Expected: FAIL — `ModuleNotFoundError: chacmd.workspace`.

- [ ] **Step 3: Write minimal implementation**

`chacmd/chacmd/workspace.py`:
```python
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class Workspace:
    """Per-job volume. Dir named by `code` (§6.4). Done-marker written atomically (§C9)."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)

    def job_dir(self, code: str) -> Path:
        return self._root / code

    def ensure_job_dir(self, job_id: str, code: str) -> Path:
        d = self.job_dir(code)
        (d / "input").mkdir(parents=True, exist_ok=True)
        (d / "output").mkdir(parents=True, exist_ok=True)
        return d

    def _done_path(self, code: str) -> Path:
        return self.job_dir(code) / "output" / ".done"

    def mark_done(self, job_id: str, code: str, meta: dict[str, Any]) -> None:
        target = self._done_path(code)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps({"job_id": job_id, **meta}))
        os.replace(tmp, target)  # atomic rename (write-then-atomic-rename, §C9)

    def is_done(self, job_id: str, code: str) -> bool:
        return self._done_path(code).exists()

    def read_done(self, job_id: str, code: str) -> dict[str, Any]:
        return json.loads(self._done_path(code).read_text())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_workspace.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chacmd/chacmd/workspace.py chacmd/tests/test_workspace.py
git commit -m "feat(chacmd): per-job volume with atomic done-marker"
```

---

### Task 17: Event ingest (bus publish + persist + state transitions)

**Files:**
- Create: `chacmd/chacmd/orchestrator/ingest.py`
- Test: `chacmd/tests/test_ingest.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_ingest.py`:
```python
import pytest
from chacmd.interfaces.db import Database
from chacmd.interfaces.eventbus import InMemoryEventBus
from chacmd.domain.repository import JobRepository, AuditRepository
from chacmd.domain.events import Event
from chacmd.domain.state import JobState
from chacmd.orchestrator.ingest import EventIngest


@pytest.fixture
async def db():
    d = Database(url="sqlite+aiosqlite:///:memory:")
    await d.create_all()
    yield d
    await d.dispose()


@pytest.mark.asyncio
async def test_ingest_publishes_persists_and_transitions(db):
    jobs = JobRepository(db)
    job = await jobs.create(code="c", goal="g", dept="d1")
    await jobs.set_state(job.id, JobState.DISPATCHING)
    await jobs.set_state(job.id, JobState.RUNNING)

    bus = InMemoryEventBus()
    ingest = EventIngest(bus, jobs, AuditRepository(db))

    got = []
    import asyncio
    async def consume():
        async for m in bus.subscribe(f"job.{job.id}.succeeded"):
            got.append(m)
            return
    task = asyncio.create_task(consume())
    await asyncio.sleep(0)

    await ingest.handle(Event(job.id, "t1", "dev", "succeeded", 3, {"result": "ok"}))
    await asyncio.wait_for(task, timeout=1)

    assert got and got[0]["kind"] == "succeeded"
    assert (await jobs.get(job.id)).state == JobState.SUCCEEDED.value
    audit = await AuditRepository(db).list_for_job(job.id)
    assert audit[-1].kind == "succeeded"


@pytest.mark.asyncio
async def test_terminal_kinds_map_to_states(db):
    jobs = JobRepository(db)
    job = await jobs.create(code="c", goal="g", dept="d1")
    await jobs.set_state(job.id, JobState.DISPATCHING)
    await jobs.set_state(job.id, JobState.RUNNING)
    ingest = EventIngest(InMemoryEventBus(), jobs, AuditRepository(db))
    await ingest.handle(Event(job.id, "t1", "dev", "interrupted", 2, {}))
    assert (await jobs.get(job.id)).state == JobState.INTERRUPTED.value
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError: chacmd.orchestrator.ingest`.

- [ ] **Step 3: Write minimal implementation**

`chacmd/chacmd/orchestrator/ingest.py`:
```python
from __future__ import annotations

from chacmd.domain.events import Event
from chacmd.domain.repository import JobRepository, AuditRepository
from chacmd.domain.state import JobState
from chacmd.interfaces.eventbus import EventBus

# Which event kinds drive a terminal/approval job-state transition.
_KIND_TO_STATE = {
    "started": JobState.RUNNING,
    "pending_approval": JobState.PENDING_APPROVAL,
    "succeeded": JobState.SUCCEEDED,
    "failed": JobState.FAILED,
    "interrupted": JobState.INTERRUPTED,
}


class EventIngest:
    """Unified event sink: publish to bus + append audit + drive job state (§6.6/§C9)."""

    def __init__(self, bus: EventBus, jobs: JobRepository, audit: AuditRepository) -> None:
        self._bus = bus
        self._jobs = jobs
        self._audit = audit

    async def handle(self, e: Event) -> None:
        await self._bus.publish(e.subject(), {"kind": e.kind, "seq": e.seq, "payload": e.payload})
        await self._audit.append(e)
        target = _KIND_TO_STATE.get(e.kind)
        if target is not None:
            job = await self._jobs.get(e.job_id)
            if job and JobState(job.state) != target:
                from chacmd.domain.state import can_transition
                if can_transition(JobState(job.state), target):
                    await self._jobs.set_state(e.job_id, target)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_ingest.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chacmd/chacmd/orchestrator/ingest.py chacmd/tests/test_ingest.py
git commit -m "feat(chacmd): event ingest (bus + audit + state transitions)"
```

---

### Task 18: Dispatcher (@nickname → authz → AgentAdapter → ingest)

**Files:**
- Create: `chacmd/chacmd/orchestrator/dispatcher.py`
- Test: `chacmd/tests/test_dispatcher.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_dispatcher.py`:
```python
import pytest
from chacmd.interfaces.db import Database
from chacmd.interfaces.eventbus import InMemoryEventBus
from chacmd.interfaces.chayuan_client import FakeChayuanClient
from chacmd.interfaces.agent_adapter import FakeAgentAdapter
from chacmd.domain.repository import JobRepository, ContainerRepository, AuditRepository
from chacmd.domain.state import JobState
from chacmd.orchestrator.ingest import EventIngest
from chacmd.orchestrator.dispatcher import Dispatcher


@pytest.fixture
async def db():
    d = Database(url="sqlite+aiosqlite:///:memory:")
    await d.create_all()
    yield d
    await d.dispose()


@pytest.mark.asyncio
async def test_dispatch_by_nickname_runs_to_success(db):
    jobs = JobRepository(db)
    containers = ContainerRepository(db)
    await containers.upsert(nickname="dev", session="s1", dept="d1")
    job = await jobs.create(code="c", goal="build app", dept="d1")

    ingest = EventIngest(InMemoryEventBus(), jobs, AuditRepository(db))
    disp = Dispatcher(
        jobs=jobs, containers=containers, chayuan=FakeChayuanClient(),
        adapter=FakeAgentAdapter(steps=["a", "b"]), ingest=ingest,
    )
    await disp.dispatch(job_id=job.id, nickname="dev", subject="u1", system_prompt="you are dev")
    assert (await jobs.get(job.id)).state == JobState.SUCCEEDED.value


@pytest.mark.asyncio
async def test_dispatch_denied_by_authz_does_not_run(db):
    jobs = JobRepository(db)
    containers = ContainerRepository(db)
    await containers.upsert(nickname="dev", session="s1", dept="d1")
    job = await jobs.create(code="c", goal="g", dept="d1")
    chayuan = FakeChayuanClient()
    chayuan.deny("u1", "container:dev", "dispatch")
    disp = Dispatcher(jobs, containers, chayuan, FakeAgentAdapter(steps=["a"]), EventIngest(InMemoryEventBus(), jobs, AuditRepository(db)))
    with pytest.raises(PermissionError):
        await disp.dispatch(job_id=job.id, nickname="dev", subject="u1", system_prompt="p")
    assert (await jobs.get(job.id)).state == JobState.QUEUED.value


@pytest.mark.asyncio
async def test_dispatch_unknown_nickname_raises(db):
    jobs = JobRepository(db)
    containers = ContainerRepository(db)
    job = await jobs.create(code="c", goal="g", dept="d1")
    disp = Dispatcher(jobs, containers, FakeChayuanClient(), FakeAgentAdapter(steps=[]), EventIngest(InMemoryEventBus(), jobs, AuditRepository(db)))
    with pytest.raises(KeyError):
        await disp.dispatch(job_id=job.id, nickname="ghost", subject="u1", system_prompt="p")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_dispatcher.py -v`
Expected: FAIL — `ModuleNotFoundError: chacmd.orchestrator.dispatcher`.

- [ ] **Step 3: Write minimal implementation**

`chacmd/chacmd/orchestrator/dispatcher.py`:
```python
from __future__ import annotations

from chacmd.domain.repository import JobRepository, ContainerRepository
from chacmd.domain.state import JobState
from chacmd.interfaces.agent_adapter import AgentAdapter, DispatchSpec
from chacmd.interfaces.chayuan_client import ChayuanClient
from chacmd.orchestrator.ingest import EventIngest


class Dispatcher:
    """@nickname dispatch (fast path, no LLM routing in P0) → authz → AgentAdapter → ingest."""

    def __init__(
        self,
        jobs: JobRepository,
        containers: ContainerRepository,
        chayuan: ChayuanClient,
        adapter: AgentAdapter,
        ingest: EventIngest,
    ) -> None:
        self._jobs = jobs
        self._containers = containers
        self._chayuan = chayuan
        self._adapter = adapter
        self._ingest = ingest

    async def dispatch(self, job_id: str, nickname: str, subject: str, system_prompt: str) -> None:
        container = await self._containers.resolve(nickname)
        if container is None:
            raise KeyError(f"unknown nickname: {nickname}")

        allowed = await self._chayuan.authorize(subject=subject, resource=f"container:{nickname}", action="dispatch")
        if not allowed:
            raise PermissionError(f"{subject} not allowed to dispatch to {nickname}")

        job = await self._jobs.get(job_id)
        await self._jobs.set_state(job_id, JobState.DISPATCHING)
        spec = DispatchSpec(job_id=job_id, task_id=job_id, nickname=nickname, goal=job.goal, system_prompt=system_prompt)
        async for event in self._adapter.dispatch(spec):
            await self._ingest.handle(event)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_dispatcher.py -v`
Expected: PASS (all three).

- [ ] **Step 5: Commit**

```bash
git add chacmd/chacmd/orchestrator/dispatcher.py chacmd/tests/test_dispatcher.py
git commit -m "feat(chacmd): dispatcher (@nickname + authz + adapter + ingest)"
```

---

### Task 19: agent-bridge — event adapter (OpenHands JSONL → unified Event)

**Files:**
- Create: `agent-bridge/pyproject.toml`
- Create: `agent-bridge/agent_bridge/__init__.py`
- Create: `agent-bridge/agent_bridge/event_adapter.py`
- Test: `agent-bridge/tests/test_event_adapter.py`

- [ ] **Step 1: Write the failing test**

`agent-bridge/tests/test_event_adapter.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_bridge.event_adapter import openhands_line_to_event


def test_openhands_action_line_maps_to_progress():
    line = '{"observation": null, "action": "run", "args": {"command": "npm run build"}}'
    e = openhands_line_to_event(line, job_id="j1", task_id="t1", nickname="dev", seq=2)
    assert e["kind"] == "progress"
    assert e["seq"] == 2
    assert e["payload"]["action"] == "run"


def test_openhands_finish_line_maps_to_succeeded():
    line = '{"action": "finish", "args": {"outputs": {"result": "done"}}}'
    e = openhands_line_to_event(line, job_id="j1", task_id="t1", nickname="dev", seq=9)
    assert e["kind"] == "succeeded"


def test_malformed_line_maps_to_progress_raw():
    e = openhands_line_to_event("not json", job_id="j1", task_id="t1", nickname="dev", seq=1)
    assert e["kind"] == "progress"
    assert e["payload"]["raw"] == "not json"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent-bridge && python -m pytest tests/test_event_adapter.py -v`
Expected: FAIL — `ModuleNotFoundError: agent_bridge.event_adapter`.

- [ ] **Step 3: Write minimal implementation**

`agent-bridge/pyproject.toml`:
```toml
[project]
name = "agent-bridge"
version = "0.0.0"
requires-python = ">=3.12"
dependencies = ["websockets>=13"]

[project.optional-dependencies]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

`agent-bridge/agent_bridge/__init__.py`:
```python
__version__ = "0.0.0"
```

`agent-bridge/agent_bridge/event_adapter.py`:
```python
from __future__ import annotations

import json
from typing import Any

# Map OpenHands JSONL event stream (or claude stream-json) → unified Event dict (§6.6, B2).
_TERMINAL_ACTIONS = {"finish": "succeeded", "error": "failed"}


def openhands_line_to_event(line: str, job_id: str, task_id: str, nickname: str, seq: int) -> dict[str, Any]:
    try:
        obj = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return {"job_id": job_id, "task_id": task_id, "container": nickname,
                "kind": "progress", "seq": seq, "payload": {"raw": line}}

    action = obj.get("action")
    kind = _TERMINAL_ACTIONS.get(action, "progress")
    payload: dict[str, Any] = {"action": action} if action else {}
    payload.update({k: v for k, v in obj.items() if k != "action"})
    return {"job_id": job_id, "task_id": task_id, "container": nickname,
            "kind": kind, "seq": seq, "payload": payload}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent-bridge && pip install -e ".[dev]" && python -m pytest tests/test_event_adapter.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent-bridge/pyproject.toml agent-bridge/agent_bridge/__init__.py agent-bridge/agent_bridge/event_adapter.py agent-bridge/tests/test_event_adapter.py
git commit -m "feat(agent-bridge): OpenHands JSONL → unified event adapter"
```

---

### Task 20: agent-bridge — reverse-connect client (register + heartbeat loop)

**Files:**
- Create: `agent-bridge/agent_bridge/main.py`
- Test: `agent-bridge/tests/test_bridge_client.py`

- [ ] **Step 1: Write the failing test**

`agent-bridge/tests/test_bridge_client.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import json
import pytest
import websockets
from agent_bridge.main import BridgeClient


@pytest.mark.asyncio
async def test_bridge_client_registers_on_connect():
    received = []

    async def handler(ws):
        async for raw in ws:
            received.append(json.loads(raw))
            if len(received) >= 1:
                return

    server = await websockets.serve(handler, "127.0.0.1", 8788)
    try:
        client = BridgeClient(url="ws://127.0.0.1:8788", nickname="dev", dept="d1")
        await client.connect_and_register()
        for _ in range(50):                 # wait for server to process (avoid race)
            if received:
                break
            await asyncio.sleep(0.02)
        await client.close()
        assert received and received[0]["type"] == "register"
        assert received[0]["nickname"] == "dev"
        assert "ip" not in received[0]  # bridge dials out; no IP is ever sent
    finally:
        server.close()
        await server.wait_closed()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd agent-bridge && python -m pytest tests/test_bridge_client.py -v`
Expected: FAIL — `ModuleNotFoundError: agent_bridge.main`.

- [ ] **Step 3: Write minimal implementation**

`agent-bridge/agent_bridge/main.py`:
```python
from __future__ import annotations

import asyncio
import json

import websockets


class BridgeClient:
    """子容器 resident service: reverse-connect to gateway, register by nickname, heartbeat.

    The container DIALS OUT (NAT-friendly). It never advertises an IP; identity is the nickname.
    """

    def __init__(self, url: str, nickname: str, dept: str, heartbeat_s: float = 10.0) -> None:
        self._url = url.rstrip("/")
        self._nickname = nickname
        self._dept = dept
        self._heartbeat_s = heartbeat_s
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._hb_task: asyncio.Task | None = None

    async def connect_and_register(self) -> None:
        self._ws = await websockets.connect(f"{self._url}/bridge")
        await self._send("register", {})

    async def start_heartbeat(self) -> None:
        async def loop():
            while self._ws is not None:
                await self._send("heartbeat", {})
                await asyncio.sleep(self._heartbeat_s)
        self._hb_task = asyncio.create_task(loop())

    async def _send(self, type_: str, data: dict) -> None:
        assert self._ws is not None
        await self._ws.send(json.dumps({"type": type_, "nickname": self._nickname, "dept": self._dept, "data": data}))

    async def close(self) -> None:
        if self._hb_task:
            self._hb_task.cancel()
        if self._ws:
            await self._ws.close()
            self._ws = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd agent-bridge && python -m pytest tests/test_bridge_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent-bridge/agent_bridge/main.py agent-bridge/tests/test_bridge_client.py
git commit -m "feat(agent-bridge): reverse-connect client (register + heartbeat, no IP)"
```

---

### Task 21: FastAPI app + OpenAPI + Task-as-API `code` endpoints

**Files:**
- Create: `chacmd/chacmd/api/__init__.py`
- Create: `chacmd/chacmd/api/schemas.py`
- Create: `chacmd/chacmd/api/app.py`
- Test: `chacmd/tests/test_api.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_api.py`:
```python
import pytest
from httpx import AsyncClient, ASGITransport
from chacmd.interfaces.db import Database
from chacmd.api.app import create_app


@pytest.fixture
async def client():
    db = Database(url="sqlite+aiosqlite:///:memory:")
    await db.create_all()
    app = create_app(db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await db.dispose()


@pytest.mark.asyncio
async def test_openapi_served(client):
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/api/v1/tasks/{code}/runs" in resp.json()["paths"]


@pytest.mark.asyncio
async def test_create_run_by_code_returns_job_id(client):
    resp = await client.post("/api/v1/tasks/world-rank-app/runs",
                             json={"goal": "build ranking app", "dept": "d1"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["job_id"]
    assert body["state"] == "queued"


@pytest.mark.asyncio
async def test_get_run_status(client):
    created = await client.post("/api/v1/tasks/c/runs", json={"goal": "g", "dept": "d1"})
    job_id = created.json()["job_id"]
    resp = await client.get(f"/api/v1/runs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["code"] == "c"


@pytest.mark.asyncio
async def test_list_containers(client):
    resp = await client.get("/api/v1/containers")
    assert resp.status_code == 200
    assert resp.json() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: chacmd.api.app`.

- [ ] **Step 3: Write minimal implementation**

`chacmd/chacmd/api/__init__.py`:
```python
```

`chacmd/chacmd/api/schemas.py`:
```python
from __future__ import annotations

from pydantic import BaseModel


class CreateRunRequest(BaseModel):
    goal: str
    dept: str


class RunCreated(BaseModel):
    job_id: str
    state: str


class RunStatus(BaseModel):
    job_id: str
    code: str
    goal: str
    dept: str
    state: str


class ContainerOut(BaseModel):
    nickname: str
    dept: str
```

`chacmd/chacmd/api/app.py`:
```python
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from sqlalchemy import select

from chacmd.interfaces.db import Database
from chacmd.domain.models import ContainerReg
from chacmd.domain.repository import JobRepository
from chacmd.api.schemas import CreateRunRequest, RunCreated, RunStatus, ContainerOut


def create_app(db: Database) -> FastAPI:
    app = FastAPI(title="ChaCMD Orchestrator", version="0.1.0")
    jobs = JobRepository(db)

    @app.post("/api/v1/tasks/{code}/runs", response_model=RunCreated, status_code=201)
    async def create_run(code: str, req: CreateRunRequest) -> RunCreated:
        # #20 Task-as-API: external caller passes `code` → spawn a new run instance.
        job = await jobs.create(code=code, goal=req.goal, dept=req.dept)
        return RunCreated(job_id=job.id, state=job.state)

    @app.get("/api/v1/runs/{job_id}", response_model=RunStatus)
    async def get_run(job_id: str) -> RunStatus:
        job = await jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="run not found")
        return RunStatus(job_id=job.id, code=job.code, goal=job.goal, dept=job.dept, state=job.state)

    @app.get("/api/v1/containers", response_model=list[ContainerOut])
    async def list_containers() -> list[ContainerOut]:
        async with db.session() as s:
            rows = await s.execute(select(ContainerReg))
            return [ContainerOut(nickname=r.nickname, dept=r.dept) for r in rows.scalars()]

    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_api.py -v`
Expected: PASS (all four).

- [ ] **Step 5: Commit**

```bash
git add chacmd/chacmd/api/__init__.py chacmd/chacmd/api/schemas.py chacmd/chacmd/api/app.py chacmd/tests/test_api.py
git commit -m "feat(chacmd): FastAPI app + OpenAPI + Task-as-API code endpoints"
```

---

### Task 22: Composition root + CLI entry (`python -m chacmd.cli start`)

**Files:**
- Create: `chacmd/chacmd/config.py`
- Create: `chacmd/chacmd/container.py`
- Create: `chacmd/chacmd/cli.py`
- Test: `chacmd/tests/test_container.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_container.py`:
```python
import pytest
from chacmd.config import Settings
from chacmd.container import build_container


@pytest.mark.asyncio
async def test_container_wires_default_impls_and_is_swappable():
    settings = Settings(db_url="sqlite+aiosqlite:///:memory:", chayuan_base_url="http://x", chayuan_web_url="http://w")
    c = await build_container(settings, use_fakes=True)
    # I1..I10 present:
    assert c.chayuan is not None       # I1
    assert c.db.dialect == "sqlite"    # I2
    assert c.crypto is not None        # I3
    assert c.registry is not None      # I4
    assert c.bus is not None           # I6
    assert c.transport is not None     # I10
    assert c.adapter is not None       # I5
    assert c.sandbox is not None       # I7
    assert c.auth is not None          # I8
    await c.db.dispose()


@pytest.mark.asyncio
async def test_swap_config_source_without_changing_callers():
    # Prove I4 swap-point: replace ConfigSource impl, callers unaffected.
    from chacmd.interfaces.registry import InProcessConfigSource
    settings = Settings(db_url="sqlite+aiosqlite:///:memory:", chayuan_base_url="http://x", chayuan_web_url="http://w")
    c = await build_container(settings, use_fakes=True)
    c.config = InProcessConfigSource({"k": "v2"})
    assert c.config.get("k") == "v2"
    await c.db.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_container.py -v`
Expected: FAIL — `ModuleNotFoundError: chacmd.config`.

- [ ] **Step 3: Write minimal implementation**

`chacmd/chacmd/config.py`:
```python
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
```

`chacmd/chacmd/container.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chacmd.config import Settings
from chacmd.interfaces.db import Database
from chacmd.interfaces.crypto import StdCrypto
from chacmd.interfaces.registry import InProcessServiceRegistry, InProcessConfigSource
from chacmd.interfaces.eventbus import InMemoryEventBus
from chacmd.interfaces.transport import InProcessTransport
from chacmd.interfaces.agent_adapter import FakeAgentAdapter
from chacmd.interfaces.sandbox import FakeSandbox
from chacmd.interfaces.chayuan_client import FakeChayuanClient, HttpChayuanClient
from chacmd.interfaces.auth import FakeAuthProvider, ChayuanAuthProvider
from chacmd.domain.repository import JobRepository, ContainerRepository, AuditRepository
from chacmd.orchestrator.ingest import EventIngest
from chacmd.orchestrator.dispatcher import Dispatcher
from chacmd.workspace import Workspace


@dataclass
class Container:
    settings: Settings
    db: Database
    chayuan: Any
    crypto: Any
    registry: Any
    config: Any
    bus: Any
    transport: Any
    adapter: Any
    sandbox: Any
    auth: Any
    jobs: JobRepository
    containers: ContainerRepository
    audit: AuditRepository
    ingest: EventIngest
    dispatcher: Dispatcher
    workspace: Workspace


async def build_container(settings: Settings, use_fakes: bool = False) -> Container:
    db = Database(url=settings.db_url)
    await db.create_all()

    if use_fakes:
        chayuan = FakeChayuanClient(web_url=settings.chayuan_web_url)
        adapter = FakeAgentAdapter(steps=["step-1", "step-2"])
        auth = FakeAuthProvider()
    else:
        chayuan = HttpChayuanClient(base_url=settings.chayuan_base_url, web_url=settings.chayuan_web_url)
        adapter = FakeAgentAdapter(steps=["step-1"])  # M2: real OpenHandsAdapter wired in M3
        auth = ChayuanAuthProvider(chayuan)

    jobs = JobRepository(db)
    containers = ContainerRepository(db)
    audit = AuditRepository(db)
    bus = InMemoryEventBus()
    ingest = EventIngest(bus, jobs, audit)
    dispatcher = Dispatcher(jobs, containers, chayuan, adapter, ingest)

    return Container(
        settings=settings, db=db, chayuan=chayuan, crypto=StdCrypto(secret=b"dev"),
        registry=InProcessServiceRegistry(), config=InProcessConfigSource({}),
        bus=bus, transport=InProcessTransport(), adapter=adapter, sandbox=FakeSandbox(),
        auth=auth, jobs=jobs, containers=containers, audit=audit, ingest=ingest,
        dispatcher=dispatcher, workspace=Workspace(root=Path(settings.workspace_root)),
    )
```

`chacmd/chacmd/cli.py`:
```python
from __future__ import annotations

import argparse
import asyncio

import uvicorn

from chacmd.config import Settings
from chacmd.container import build_container
from chacmd.api.app import create_app
from chacmd.gateway.bridge_gateway import BridgeGateway


async def _serve(settings: Settings) -> None:
    container = await build_container(settings, use_fakes=False)
    gateway = BridgeGateway(container.containers, host=settings.gateway_host, port=settings.gateway_port)
    gateway.on_event(lambda env: container.ingest.handle(_env_to_event(env)))
    await gateway.start()
    app = create_app(container.db)
    config = uvicorn.Config(app, host=settings.api_host, port=settings.api_port, log_level="info")
    await uvicorn.Server(config).serve()
    await gateway.stop()


def _env_to_event(env):
    from chacmd.domain.events import Event
    d = env.data
    return Event(d["job_id"], d["task_id"], env.nickname, d["kind"], d["seq"], d.get("payload", {}))


def main() -> None:
    parser = argparse.ArgumentParser(prog="chacmd")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("start", help="start the ChaCMD orchestrator + gateway + API")
    args = parser.parse_args()
    if args.command == "start":
        asyncio.run(_serve(Settings.from_env()))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_container.py -v`
Expected: PASS (both).

- [ ] **Step 5: Commit**

```bash
git add chacmd/chacmd/config.py chacmd/chacmd/container.py chacmd/chacmd/cli.py chacmd/tests/test_container.py
git commit -m "feat(chacmd): composition root + cli start entry"
```

---

### Task 23: End-to-end integration test (dispatch → events → success → volume)

**Files:**
- Test: `chacmd/tests/test_e2e_dispatch.py`

- [ ] **Step 1: Write the failing test**

`chacmd/tests/test_e2e_dispatch.py`:
```python
import asyncio
import pytest
from pathlib import Path
from chacmd.config import Settings
from chacmd.container import build_container
from chacmd.domain.state import JobState


@pytest.mark.asyncio
async def test_full_loop_dispatch_stream_persist_volume(tmp_path):
    settings = Settings(
        db_url="sqlite+aiosqlite:///:memory:",
        chayuan_base_url="http://x", chayuan_web_url="http://w",
        workspace_root=str(tmp_path),
    )
    c = await build_container(settings, use_fakes=True)

    # A container comes online (reverse-registered).
    await c.containers.upsert(nickname="dev", session="s1", dept="d1")

    # Create a job by code and prepare its volume.
    job = await c.jobs.create(code="world-rank-app", goal="build ranking app", dept="d1")
    c.workspace.ensure_job_dir(job_id=job.id, code="world-rank-app")

    # Subscribe to the success subject BEFORE dispatch.
    seen = []
    async def watch():
        async for m in c.bus.subscribe(f"job.{job.id}.succeeded"):
            seen.append(m); return
    watcher = asyncio.create_task(watch())
    await asyncio.sleep(0)

    # Dispatch by nickname.
    await c.dispatcher.dispatch(job_id=job.id, nickname="dev", subject="u1", system_prompt="you are dev")
    await asyncio.wait_for(watcher, timeout=2)

    # Assert: state succeeded, audit trail present, we can mark the produce done atomically.
    assert (await c.jobs.get(job.id)).state == JobState.SUCCEEDED.value
    audit = await c.audit.list_for_job(job.id)
    assert [a.kind for a in audit][0] == "started"
    assert [a.kind for a in audit][-1] == "succeeded"
    c.workspace.mark_done(job.id, "world-rank-app", {"artifact": "output/app"})
    assert c.workspace.is_done(job.id, "world-rank-app") is True

    await c.db.dispose()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chacmd && python -m pytest tests/test_e2e_dispatch.py -v`
Expected: FAIL initially only if any wiring is missing; if all prior tasks are complete it may pass immediately. If it fails, fix the wiring gap it reveals (do not modify the test).

- [ ] **Step 3: Write minimal implementation**

No new code expected — this test exercises existing wiring. If it fails, the failure names the missing seam (e.g., subject mismatch); fix that module, not the test.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chacmd && python -m pytest tests/test_e2e_dispatch.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add chacmd/tests/test_e2e_dispatch.py
git commit -m "test(chacmd): end-to-end dispatch → stream → persist → volume"
```

---

### Task 24: Full suite + lint gate

**Files:**
- Create: `chacmd/ruff.toml`

- [ ] **Step 1: Add lint config**

`chacmd/ruff.toml`:
```toml
line-length = 120
target-version = "py312"

[lint]
select = ["E", "F", "I", "UP", "B"]
ignore = ["B008"]  # FastAPI Depends() default pattern
```

- [ ] **Step 2: Run the full test suite (both packages)**

Run:
```bash
cd chacmd && python -m pytest -v
cd ../agent-bridge && python -m pytest -v
```
Expected: ALL tests PASS.

- [ ] **Step 3: Run lint**

Run: `cd chacmd && ruff check .`
Expected: no errors (fix any surfaced).

- [ ] **Step 4: Grep-verify the no-IP invariant**

Run: `grep -rniE "([0-9]{1,3}\.){3}[0-9]{1,3}" chacmd/chacmd agent-bridge/agent_bridge | grep -v "127.0.0.1" | grep -v test`
Expected: no matches (only allowed loopback in config defaults; **no container IP hardcoded**).

- [ ] **Step 5: Commit**

```bash
git add chacmd/ruff.toml
git commit -m "chore(chacmd): lint gate + full-suite green + no-IP invariant check"
```

---

## Self-Review (run after writing; record findings)

**1. Spec coverage (requirements → task):**
- I1 ChayuanClient → Task 7 ✓ | I2 DB → Task 2 ✓ | I3 Crypto → Task 3 ✓ | I4 Registry+Config → Task 6 ✓ | I5 AgentAdapter → Task 9 ✓ | I6 EventBus → Task 5 ✓ | I7 Sandbox → Task 10 ✓ | I8 Auth → Task 8 ✓ | I10 Transport/no-IP → Task 4 ✓
- I9 frontend seam → OUT OF SCOPE (frontend plan, noted).
- State machine incl. pending_approval → Task 11 ✓ | Job/Task/registry/audit models → Task 12 ✓
- Reverse-connect registration (no IP) → Task 13/15/20 ✓ | lease dead-judge decoupled from bus → Task 14 ✓
- @nickname dispatch + authz (fast path, no LLM routing P0) → Task 18 ✓
- Event stream adapter (OpenHands JSONL) → Task 19 ✓ | ingest publish+persist+transition → Task 17 ✓
- per-job volume + atomic done-marker → Task 16 ✓ | Task-as-API `code` endpoints + OpenAPI → Task 21 ✓
- cli `python -m chacmd.cli start` → Task 22 ✓ | end-to-end → Task 23 ✓ | no-IP grep invariant → Task 24 ✓
- **Gaps deferred by design (not omissions):** real OpenHands adapter, real rootless sandbox execution, budget-kill, OTel, iframe preview, approval UI, real Postgres/NATS soak → M3/M4 plans.

**2. Placeholder scan:** No "TBD/TODO/implement later". Task 3 `encrypt/decrypt` is an explicit identity pair guarded behind I3 (only vault uses it, P1) — documented, not a hidden placeholder. Task 22 non-fake path wires `FakeAgentAdapter` deliberately (real OpenHands = M3) — documented.

**3. Type consistency:** `Event(job_id, task_id, container, kind, seq, payload)` used identically in Tasks 9/12/17/19/22/23. `Envelope(type,nickname,dept,data)` identical in 13/15/20. `DispatchSpec` fields consistent 9/18. `JobState` values consistent 11/12/17/18/23. `Database.session()/create_all()/dialect` consistent 2/12/21/22. `ContainerRepository.upsert/resolve/touch` consistent 12/13/14/18/23.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-01-chacmd-p0-backend-skeleton.md`.
