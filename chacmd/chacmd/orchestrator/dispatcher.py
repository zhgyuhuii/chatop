from __future__ import annotations

from chacmd.domain.repository import ContainerRepository, JobRepository
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
        spec = DispatchSpec(
            job_id=job_id, task_id=job_id, nickname=nickname, goal=job.goal, system_prompt=system_prompt
        )
        async for event in self._adapter.dispatch(spec):
            await self._ingest.handle(event)
