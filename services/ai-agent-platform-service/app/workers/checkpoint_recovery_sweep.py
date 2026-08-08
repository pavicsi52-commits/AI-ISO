"""The checkpoint recovery sweep worker (docs/060 "LANGGRAPH":
Checkpoint Recovery; "PERFORMANCE": Checkpoint Recovery, High
Availability, Automatic Failover).

Finds every workflow run stuck ``RUNNING`` past a cutoff -- almost
certainly a crash mid-run, since a genuinely still-in-progress run
keeps advancing its own checkpoint on every completed level -- and
resumes each from its own last persisted checkpoint via
:class:`~app.langgraph.service.WorkflowPersistenceService`. **Leader-
elected** through ``shared_core.scheduler``; see
:mod:`app.workers.registrar`.

Resuming re-runs the whole graph from ``START`` -- the real, disclosed
SDK limitation :mod:`app.langgraph.approval`'s own module docstring
documents, not something this worker can work around.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.orchestrator import AgentOrchestrator
from app.clients.registry import ModelRegistry
from app.langgraph.service import WorkflowPersistenceService
from app.repositories.agent import AgentRepository
from app.repositories.profile import AgentProfileRepository
from app.repositories.workflow import AgentWorkflowRepository

logger = get_logger("app.workers.checkpoint_recovery_sweep")


class CheckpointRecoverySweepWorker:
    """Resumes every workflow run stuck ``RUNNING`` past its own cutoff."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        registry: ModelRegistry,
        *,
        stuck_after_seconds: float,
        max_workflows_per_tick: int = 50,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry
        self._stuck_after_seconds = stuck_after_seconds
        self._max_workflows_per_tick = max_workflows_per_tick

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Resume every workflow stuck ``RUNNING``; returns how many were resumed."""
        cutoff = datetime.now(UTC) - timedelta(seconds=self._stuck_after_seconds)
        async with self._session_factory() as session:
            stuck = await AgentWorkflowRepository(session).list_stuck_running(
                cutoff, limit=self._max_workflows_per_tick
            )
        resumed = 0
        for workflow in stuck:
            if await self._resume_one(workflow.id, workflow.organization_id):
                resumed += 1
        logger.info(
            "Checkpoint recovery sweep complete.",
            extra={"extra_fields": {"stuck": len(stuck), "resumed": resumed}},
        )
        return resumed

    async def _resume_one(self, workflow_id: object, organization_id: object) -> bool:
        """Resume one stuck workflow under its own session."""
        try:
            async with self._session_factory() as session:
                workflows_repo = AgentWorkflowRepository(session)
                workflow = await workflows_repo.require_in_org(organization_id, workflow_id)  # type: ignore[arg-type]

                agents_repo = AgentRepository(session)
                agents = await agents_repo.list_for_org(organization_id)  # type: ignore[arg-type]
                agents_by_type: dict[object, list[object]] = {}
                for agent in agents:
                    agents_by_type.setdefault(agent.agent_type, []).append(agent)
                profiles_by_agent_id = {}
                for agent in agents:
                    profile = await AgentProfileRepository(session).get_for_agent(agent.id)
                    if profile is not None:
                        profiles_by_agent_id[agent.id] = profile

                orchestrator = AgentOrchestrator(
                    self._registry, agents_by_type, profiles_by_agent_id
                )
                service = WorkflowPersistenceService(workflows_repo, orchestrator)
                await service.run(workflow)
                await session.commit()
            return True
        except Exception as exc:
            logger.warning(
                "A checkpoint recovery resume failed; the rest of the sweep continues.",
                extra={"extra_fields": {"workflow_id": str(workflow_id), "error": str(exc)}},
            )
            return False


__all__ = ["CheckpointRecoverySweepWorker"]
