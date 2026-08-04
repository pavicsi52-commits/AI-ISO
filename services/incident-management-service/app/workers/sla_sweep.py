"""The SLA sweep worker.

Checks every organization's running SLA clocks for warnings and
breaches. **Leader-elected** through ``shared_core.scheduler`` -- see
:mod:`app.workers.registrar`.

**One session per organization.** A failure sweeping one tenant's
clocks must not poison the transaction the next tenant's sweep needs --
and in a service whose whole purpose is timely response, one tenant
silently missing from a sweep is worse than a sweep that visibly failed
for it.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.notifications.factory import create_notification_framework
from shared_core.scheduler import Job
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.incident import Incident
from app.notifications.incident_notifications import IncidentNotificationService
from app.repositories.catalogue import IncidentPriorityRepository
from app.repositories.incident import IncidentRepository
from app.repositories.sla import SlaRepository
from app.services.sla import SlaService
from app.sla.engine import BusinessCalendar

logger = get_logger("app.workers.sla_sweep")


class SlaSweepWorker:
    """Sweeps every organization's SLA clocks for warnings and breaches."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        max_per_tick: int = 500,
        warning_percent: int = 80,
        calendar: BusinessCalendar | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._max_per_tick = max_per_tick
        self._warning_percent = warning_percent
        self._calendar = calendar or BusinessCalendar()

    async def run_job(self, _job: Job) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> dict[str, int]:
        """Sweep every organization; returns aggregate warn/breach counts."""
        organizations = await self._organizations()
        warned = breached = 0
        for organization_id in organizations:
            counts = await self._sweep(organization_id)
            warned += counts["warned"]
            breached += counts["breached"]
        logger.info(
            "SLA sweep complete.",
            extra={
                "extra_fields": {
                    "organizations": len(organizations),
                    "warned": warned,
                    "breached": breached,
                }
            },
        )
        return {"organizations": len(organizations), "warned": warned, "breached": breached}

    async def _organizations(self) -> list[UUID]:
        """Every organization with at least one incident."""
        async with self._session_factory() as session:
            statement = select(distinct(Incident.organization_id)).limit(self._max_per_tick)
            result = await session.execute(statement)
            return [row for row in result.scalars().all() if row is not None]

    async def _sweep(self, organization_id: UUID) -> dict[str, int]:
        """Sweep one organization's clocks under its own session."""
        try:
            async with self._session_factory() as session:
                notifications = IncidentNotificationService(create_notification_framework())
                service = SlaService(
                    SlaRepository(session),
                    IncidentPriorityRepository(session),
                    IncidentRepository(session),
                    notifications,
                    calendar=self._calendar,
                    warning_percent=self._warning_percent,
                )
                counts = await service.sweep(organization_id)
                await session.commit()
            return counts
        except Exception as exc:
            logger.warning(
                "An SLA sweep failed for one organization; the rest of the tick continues.",
                extra={
                    "extra_fields": {"organization_id": str(organization_id), "error": str(exc)}
                },
            )
            return {"warned": 0, "breached": 0}


__all__ = ["SlaSweepWorker"]
