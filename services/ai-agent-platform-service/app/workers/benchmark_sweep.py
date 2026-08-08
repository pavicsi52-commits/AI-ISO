"""The benchmark sweep worker (docs/060 "EVALUATION" benchmarking).

Runs a minimal health-check benchmark against every ``ACTIVE`` agent
that has not had a benchmark run in the configured window -- a real,
scheduled regression check, not just an on-demand capability. **Leader-
elected** through ``shared_core.scheduler``; see
:mod:`app.workers.registrar`.

**One session per organization.** A failure on one tenant must not
poison the transaction the next one needs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.orchestrator import AgentOrchestrator
from app.benchmarks.runner import BenchmarkCase
from app.benchmarks.service import BenchmarkService
from app.clients.registry import ModelRegistry
from app.repositories.agent import AgentRepository
from app.repositories.benchmark import AgentBenchmarkRepository
from app.repositories.profile import AgentProfileRepository

logger = get_logger("app.workers.benchmark_sweep")

_HEALTH_CHECK_CASE = BenchmarkCase(
    name="scheduled-health-check",
    request="Reply with a brief acknowledgement that you are working correctly.",
)
"""No ``expected_output`` -- a bare successful run is the only thing a
recurring health check needs to confirm."""


class BenchmarkSweepWorker:
    """Runs a scheduled health-check benchmark against agents due for one."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        registry: ModelRegistry,
        *,
        due_after_seconds: float,
        max_organizations_per_tick: int = 200,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry
        self._due_after_seconds = due_after_seconds
        self._max_organizations_per_tick = max_organizations_per_tick

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Benchmark every due agent across every organization; returns
        how many benchmarks ran."""
        async with self._session_factory() as session:
            organizations = await AgentRepository(session).list_organization_ids(
                limit=self._max_organizations_per_tick
            )
        ran = 0
        for organization_id in organizations:
            ran += await self._sweep_org(organization_id)
        logger.info(
            "Benchmark sweep complete.",
            extra={"extra_fields": {"organizations": len(organizations), "benchmarks_run": ran}},
        )
        return ran

    async def _sweep_org(self, organization_id: UUID) -> int:
        """Benchmark every due agent in one organization, under its own session."""
        try:
            since = datetime.now(UTC) - timedelta(seconds=self._due_after_seconds)
            async with self._session_factory() as session:
                agents_repo = AgentRepository(session)
                benchmarks_repo = AgentBenchmarkRepository(session)
                recently_benchmarked = await benchmarks_repo.list_agent_ids_benchmarked_since(
                    organization_id, since=since
                )
                due_agents = await agents_repo.list_active_without_recent_benchmark(
                    organization_id, agent_ids_with_recent_benchmark=recently_benchmarked
                )
                if not due_agents:
                    return 0

                profiles_by_agent_id = {}
                agents_by_type: dict[object, list[object]] = {}
                for agent in due_agents:
                    profile = await AgentProfileRepository(session).get_for_agent(agent.id)
                    if profile is None:
                        continue
                    profiles_by_agent_id[agent.id] = profile
                    agents_by_type.setdefault(agent.agent_type, []).append(agent)

                orchestrator = AgentOrchestrator(
                    self._registry, agents_by_type, profiles_by_agent_id
                )
                service = BenchmarkService(benchmarks_repo, orchestrator)

                ran = 0
                for agent in due_agents:
                    if agent.id not in profiles_by_agent_id:
                        continue
                    await service.run(
                        organization_id=organization_id,
                        agent_id=agent.id,
                        agent_type=agent.agent_type,
                        name="scheduled-health-check",
                        cases=[_HEALTH_CHECK_CASE],
                        triggered_by="benchmark-sweep",
                    )
                    ran += 1
                await session.commit()
                return ran
        except Exception as exc:
            logger.warning(
                "A benchmark sweep failed for one organization; the rest of the tick continues.",
                extra={
                    "extra_fields": {"organization_id": str(organization_id), "error": str(exc)}
                },
            )
            return 0


__all__ = ["BenchmarkSweepWorker"]
