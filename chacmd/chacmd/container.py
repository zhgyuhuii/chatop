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
