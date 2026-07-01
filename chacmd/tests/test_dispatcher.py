import pytest

from chacmd.domain.repository import AuditRepository, ContainerRepository, JobRepository
from chacmd.domain.state import JobState
from chacmd.interfaces.agent_adapter import FakeAgentAdapter
from chacmd.interfaces.chayuan_client import FakeChayuanClient
from chacmd.interfaces.db import Database
from chacmd.interfaces.eventbus import InMemoryEventBus
from chacmd.orchestrator.dispatcher import Dispatcher
from chacmd.orchestrator.ingest import EventIngest


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
    disp = Dispatcher(
        jobs, containers, chayuan, FakeAgentAdapter(steps=["a"]),
        EventIngest(InMemoryEventBus(), jobs, AuditRepository(db)),
    )
    with pytest.raises(PermissionError):
        await disp.dispatch(job_id=job.id, nickname="dev", subject="u1", system_prompt="p")
    assert (await jobs.get(job.id)).state == JobState.QUEUED.value


@pytest.mark.asyncio
async def test_dispatch_unknown_nickname_raises(db):
    jobs = JobRepository(db)
    containers = ContainerRepository(db)
    job = await jobs.create(code="c", goal="g", dept="d1")
    disp = Dispatcher(
        jobs, containers, FakeChayuanClient(), FakeAgentAdapter(steps=[]),
        EventIngest(InMemoryEventBus(), jobs, AuditRepository(db)),
    )
    with pytest.raises(KeyError):
        await disp.dispatch(job_id=job.id, nickname="ghost", subject="u1", system_prompt="p")


@pytest.mark.asyncio
async def test_dispatch_unknown_job_raises(db):
    jobs = JobRepository(db)
    containers = ContainerRepository(db)
    await containers.upsert(nickname="dev", session="s1", dept="d1")
    disp = Dispatcher(
        jobs, containers, FakeChayuanClient(), FakeAgentAdapter(steps=["a"]),
        EventIngest(InMemoryEventBus(), jobs, AuditRepository(db)),
    )
    with pytest.raises(KeyError):
        await disp.dispatch(job_id="does-not-exist", nickname="dev", subject="u1", system_prompt="p")
