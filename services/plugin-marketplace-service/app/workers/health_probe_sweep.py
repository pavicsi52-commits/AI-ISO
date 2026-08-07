"""The plugin installation health-probe sweep worker.

Probes every active plugin installation across every organization, in
one tick. **Leader-elected** through ``shared_core.scheduler`` -- see
:mod:`app.workers.registrar`.

**One session per installation.** A single installation's own probe (a
real outbound HTTP check, when a ``health_check_url`` is configured)
must not poison the transaction the next installation's own probe
needs, and a probe silently skipped is worse than one that visibly
failed again.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from shared_core.logging.logger import get_logger
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.events.plugin_events import SOURCE_SERVICE, PluginHealthChangedEvent
from app.repositories.health import PluginHealthRepository
from app.repositories.installation import PluginInstallationRepository
from app.services.health import PluginHealthService
from app.types import EventPublisher

logger = get_logger("app.workers.health_probe_sweep")


class HealthProbeSweepWorker:
    """Probes every active plugin installation, across every organization."""

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
        """Probe every active installation; returns how many were probed."""
        installation_ids = await self._due_installations()
        probed = 0
        for installation_id in installation_ids:
            if await self._probe_one(installation_id):
                probed += 1
        logger.info(
            "Plugin health-probe sweep complete.",
            extra={"extra_fields": {"due": len(installation_ids), "probed": probed}},
        )
        return probed

    async def _due_installations(self) -> list[UUID]:
        async with self._session_factory() as session:
            rows = await PluginInstallationRepository(session).list_all_active(
                limit=self._max_per_tick
            )
            return [row.id for row in rows]

    async def _probe_one(self, installation_id: UUID) -> bool:
        try:
            async with self._session_factory() as session:
                installations = PluginInstallationRepository(session)
                installation = await installations.require_by_id(installation_id)
                health = PluginHealthService(
                    PluginHealthRepository(session),
                    timeout_seconds=self._timeout_seconds,
                    failure_threshold=self._failure_threshold,
                )
                result = await health.probe(installation)
                await session.commit()
                if result.recovery_attempted:
                    await self._publish_event(
                        PluginHealthChangedEvent(
                            source_service=SOURCE_SERVICE,
                            organization_id=installation.organization_id,
                            payload={
                                "installation_id": str(installation.id),
                                "status": str(result.status),
                                "recovery_attempted": True,
                            },
                        )
                    )
            return True
        except Exception as exc:
            logger.warning(
                "A plugin health probe failed; the rest of the sweep continues.",
                extra={
                    "extra_fields": {"installation_id": str(installation_id), "error": str(exc)}
                },
            )
            return False

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)


__all__ = ["HealthProbeSweepWorker"]
