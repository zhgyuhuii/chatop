from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from chacmd.domain.events import Event
from chacmd.domain.models import AuditEvent, ContainerReg, Job
from chacmd.domain.state import JobState, transition
from chacmd.interfaces.db import Database


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
                row.last_heartbeat = datetime.now(UTC)
            await s.commit()

    async def resolve(self, nickname: str) -> ContainerReg | None:
        async with self._db.session() as s:
            return await s.get(ContainerReg, nickname)

    async def touch(self, nickname: str) -> None:
        async with self._db.session() as s:
            row = await s.get(ContainerReg, nickname)
            if row:
                row.last_heartbeat = datetime.now(UTC)
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
