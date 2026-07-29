"""The statistics rollup worker.

Recomputes every organization's
:class:`~app.models.graph_statistics.GraphStatistics` row from the graph
and the sync history.

**Leader-elected** through ``shared_core.scheduler`` -- see
:mod:`app.workers.registrar` for why that is the right answer here and
was the wrong one for ``services/dashboard-service``'s refresh loop.

**One session per organization.** A failure on one tenant must not
poison the transaction the next one needs.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.config.cache import get_settings as get_shared_settings
from shared_core.config.settings import Neo4jSettings
from shared_core.logging.logger import get_logger
from shared_core.scheduler import Job
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config.settings import KnowledgeGraphServiceSettings
from app.digital_twin.twin import DigitalTwinService
from app.graph.client import GraphClient, create_neo4j_driver
from app.graph.repository import GraphRepository
from app.models.graph_sync_job import GraphSyncJob
from app.repositories.graph_metadata import GraphMetadataRepository
from app.repositories.graph_statistics import GraphStatisticsRepository
from app.repositories.graph_sync_job import GraphSyncJobRepository
from app.services.statistics import StatisticsService

logger = get_logger("app.workers.statistics")


class StatisticsWorker:
    """Recomputes every organization's graph statistics."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        graph_settings: KnowledgeGraphServiceSettings,
        max_per_tick: int = 200,
    ) -> None:
        self._session_factory = session_factory
        self._settings = graph_settings
        self._max_per_tick = max_per_tick

    async def run_job(self, _job: Job) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``.

        The framework calls a job with the :class:`Job` itself and
        expects nothing back, while :meth:`tick` returns a count for
        direct testing. This adapter keeps both honest instead of
        bending one to fit the other -- and its existence is why a
        signature mismatch cannot reach production as "the scheduler
        silently never fired".
        """
        await self.tick()

    async def tick(self) -> int:
        """Recompute every organization's rollup; returns how many succeeded.

        Builds its own Neo4j driver rather than reaching into the
        application state: a scheduled job may run in a worker process
        that never built a FastAPI app, so depending on ``app.state``
        would work in tests and fail in the deployment shape that
        actually matters.
        """
        driver = create_neo4j_driver(_neo4j_settings(), enabled=self._settings.neo4j_enabled)
        client = GraphClient(
            driver,
            database=self._settings.neo4j_database,
            max_records=self._settings.max_result_nodes,
            timeout_seconds=self._settings.query_timeout_seconds,
            enabled=self._settings.neo4j_enabled,
        )
        try:
            organizations = await self._organizations()
            done = 0
            for organization_id in organizations:
                if await self._recompute(organization_id, client):
                    done += 1
            logger.info(
                "Graph statistics rollup complete.",
                extra={
                    "extra_fields": {
                        "organizations": len(organizations),
                        "succeeded": done,
                    }
                },
            )
            return done
        finally:
            if driver is not None:
                await driver.close()

    async def _organizations(self) -> list[UUID]:
        """Every organization with synchronization history.

        Derived from the sync-job table rather than from the graph:
        Neo4j has no cheap "distinct organization" query, and an
        organization the graph knows about has always been synced at
        least once.
        """
        async with self._session_factory() as session:
            statement = (
                select(distinct(GraphSyncJob.organization_id))
                .where(GraphSyncJob.deleted_at.is_(None))
                .limit(self._max_per_tick)
            )
            result = await session.execute(statement)
            return [row for row in result.scalars().all() if row is not None]

    async def _recompute(self, organization_id: UUID, client: GraphClient) -> bool:
        """Recompute one organization's rollup under its own session."""
        try:
            async with self._session_factory() as session:
                graph = GraphRepository(
                    client,
                    max_depth=self._settings.max_traversal_depth,
                    max_nodes=self._settings.max_result_nodes,
                )
                metadata = GraphMetadataRepository(session)
                service = StatisticsService(
                    graph,
                    GraphStatisticsRepository(session),
                    metadata,
                    GraphSyncJobRepository(session),
                    DigitalTwinService(graph, metadata),
                    max_nodes=self._settings.analytics_max_nodes,
                )
                await service.refresh(organization_id)
                await session.commit()
            return True
        except Exception as exc:
            logger.warning(
                "A graph statistics rollup failed; the rest of the tick continues.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "error": str(exc),
                    }
                },
            )
            return False


def _neo4j_settings() -> Neo4jSettings:
    """The shared Neo4j settings section.

    Read fresh rather than captured at construction so a worker started
    before configuration was complete still picks it up.
    """
    return get_shared_settings().neo4j


__all__ = ["StatisticsWorker"]
