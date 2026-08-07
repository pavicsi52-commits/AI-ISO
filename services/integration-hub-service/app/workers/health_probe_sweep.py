"""The connector health-probe sweep worker.

Probes every enabled connector across every organization, in one tick.
**Leader-elected** through ``shared_core.scheduler`` -- see
:mod:`app.workers.registrar`.

**One session per connector.** A single connector's own probe (a real
outbound HTTP/TCP check) must not poison the transaction the next
connector's own probe needs, and a probe silently skipped is worse than
one that visibly failed again.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.enums.health_status import HealthStatus
from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.events.hub_events import SOURCE_SERVICE, ConnectorHealthChangedEvent
from app.repositories.connector import (
    ConnectorCategoryRepository,
    ConnectorRepository,
    ConnectorVersionRepository,
)
from app.repositories.health import ConnectorHealthRepository
from app.services.connector import ConnectorService
from app.services.health import HealthService
from app.types import EventPublisher

logger = get_logger("app.workers.health_probe_sweep")


class HealthProbeSweepWorker:
    """Probes every enabled connector, across every organization."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        timeout_seconds: float,
        failure_threshold: int,
        max_per_tick: int = 500,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._timeout_seconds = timeout_seconds
        self._failure_threshold = failure_threshold
        self._max_per_tick = max_per_tick
        self._publish = publish_event

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Probe every enabled connector; returns how many were probed."""
        connector_ids = await self._due_connectors()
        probed = 0
        for connector_id in connector_ids:
            if await self._probe_one(connector_id):
                probed += 1
        logger.info(
            "Connector health-probe sweep complete.",
            extra={"extra_fields": {"due": len(connector_ids), "probed": probed}},
        )
        return probed

    async def _due_connectors(self) -> list[UUID]:
        async with self._session_factory() as session:
            rows = await ConnectorRepository(session).list_all_enabled(limit=self._max_per_tick)
            return [row.id for row in rows]

    async def _probe_one(self, connector_id: UUID) -> bool:
        try:
            async with self._session_factory() as session:
                connectors = ConnectorService(
                    ConnectorRepository(session),
                    ConnectorVersionRepository(session),
                    ConnectorCategoryRepository(session),
                )
                connector = await ConnectorRepository(session).require_by_id(connector_id)
                was_healthy = connector.consecutive_failures == 0
                health = HealthService(
                    ConnectorHealthRepository(session),
                    timeout_seconds=self._timeout_seconds,
                    failure_threshold=self._failure_threshold,
                )
                result = await health.probe(connector)
                succeeded = result.status == HealthStatus.HEALTHY
                await connectors.record_health_outcome(connector, succeeded=succeeded)
                await session.commit()
                if was_healthy != succeeded:
                    await self._publish_event(
                        ConnectorHealthChangedEvent(
                            source_service=SOURCE_SERVICE,
                            organization_id=connector.organization_id,
                            payload={
                                "connector_id": str(connector.id),
                                "status": str(result.status),
                                "recovery_attempted": result.recovery_attempted,
                            },
                        )
                    )
            return True
        except Exception as exc:
            logger.warning(
                "A connector health probe failed; the rest of the sweep continues.",
                extra={"extra_fields": {"connector_id": str(connector_id), "error": str(exc)}},
            )
            return False

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)


__all__ = ["HealthProbeSweepWorker"]
