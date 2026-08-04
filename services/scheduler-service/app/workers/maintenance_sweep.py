"""The maintenance sweep worker.

Announces ``MaintenanceStarted``/``MaintenanceEnded`` for windows that
began or ended within the last tick interval. **Leader-elected** through
``shared_core.scheduler`` -- see :mod:`app.workers.registrar`.

**Detected by boundary, not by persisted state.** A window has no
"currently announced" flag of its own -- rather than track one, this
worker fires ``MaintenanceStarted`` for any window whose ``starts_at``
falls within ``[now - interval, now]``, and ``MaintenanceEnded`` the same
way for ``ends_at``. Run at the configured
``maintenance_sweep_seconds`` interval, every boundary crossing is
caught exactly once -- a shorter interval than a window's own duration
is assumed, the same assumption every fixed-tick sweep in this codebase
makes about the thing it is watching for.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.scheduler import Job
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.events.scheduler_events import (
    SOURCE_SERVICE,
    MaintenanceEndedEvent,
    MaintenanceStartedEvent,
)
from app.models.maintenance import MaintenanceWindow
from app.repositories.maintenance import MaintenanceWindowRepository

logger = get_logger("app.workers.maintenance_sweep")


class MaintenanceSweepWorker:
    """Announces maintenance windows opening and closing."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        max_per_tick: int = 200,
        interval_seconds: int = 3_600,
        publish_event: Any = None,
    ) -> None:
        self._session_factory = session_factory
        self._max_per_tick = max_per_tick
        self._interval_seconds = interval_seconds
        self._publish = publish_event

    async def run_job(self, _job: Job) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> dict[str, int]:
        """Sweep every organization; returns started/ended counts."""
        organizations = await self._organizations()
        started = ended = 0
        for organization_id in organizations:
            counts = await self._sweep(organization_id)
            started += counts["started"]
            ended += counts["ended"]
        logger.info(
            "Maintenance sweep complete.",
            extra={
                "extra_fields": {
                    "organizations": len(organizations),
                    "started": started,
                    "ended": ended,
                }
            },
        )
        return {"organizations": len(organizations), "started": started, "ended": ended}

    async def _organizations(self) -> list[UUID]:
        """Every organization with at least one maintenance window."""
        async with self._session_factory() as session:
            statement = select(distinct(MaintenanceWindow.organization_id)).limit(
                self._max_per_tick
            )
            result = await session.execute(statement)
            return [row for row in result.scalars().all() if row is not None]

    async def _sweep(self, organization_id: UUID) -> dict[str, int]:
        """Sweep one organization's windows under its own session."""
        try:
            now = datetime.now(UTC)
            since = now - timedelta(seconds=self._interval_seconds)
            async with self._session_factory() as session:
                windows = MaintenanceWindowRepository(session)
                all_windows = await windows.list_for_org(organization_id, limit=self._max_per_tick)

                started = ended = 0
                for window in all_windows:
                    if since <= window.starts_at <= now:
                        await self._announce(
                            organization_id, window, event_cls=MaintenanceStartedEvent
                        )
                        started += 1
                    if since <= window.ends_at <= now:
                        await self._announce(
                            organization_id, window, event_cls=MaintenanceEndedEvent
                        )
                        ended += 1
            return {"started": started, "ended": ended}
        except Exception as exc:
            logger.warning(
                "A maintenance sweep failed for one organization; the rest of the tick continues.",
                extra={
                    "extra_fields": {"organization_id": str(organization_id), "error": str(exc)}
                },
            )
            return {"started": 0, "ended": 0}

    async def _announce(
        self,
        organization_id: UUID,
        window: MaintenanceWindow,
        *,
        event_cls: type[MaintenanceStartedEvent] | type[MaintenanceEndedEvent],
    ) -> None:
        """Publish one boundary-crossing event.

        No per-user notification accompanies this -- a maintenance
        window carries no owner or subscriber list of its own to notify,
        unlike a job's ``owner_id``. The event itself is what downstream
        services (docs/054's own "PLATFORM INTEGRATIONS") react to.
        """
        if self._publish is not None:
            await self._publish(
                event_cls(
                    source_service=SOURCE_SERVICE,
                    payload={
                        "organization_id": str(organization_id),
                        "window_id": str(window.id),
                        "title": window.title,
                    },
                )
            )


__all__ = ["MaintenanceSweepWorker"]
