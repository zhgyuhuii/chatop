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
