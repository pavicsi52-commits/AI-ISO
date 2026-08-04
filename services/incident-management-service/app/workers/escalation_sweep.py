"""The escalation sweep worker.

Evaluates the escalation ladder for every open incident in every
organization, firing any rung that has come due since the last check.
**Leader-elected** through ``shared_core.scheduler`` -- see
:mod:`app.workers.registrar`.

Runs independently of the SLA sweep even though escalation is driven by
SLA breaches: the two are separate ticks with separate intervals
(escalation runs far more often -- see
``app/config/settings.py``'s ``escalation_sweep_seconds`` versus
``sla_sweep_seconds``) because a page five minutes late is a real cost
this service exists to prevent, while an SLA warning does not carry the
same urgency.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.notifications.factory import create_notification_framework
from shared_core.scheduler import Job
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import incident_priority_of
from app.models.incident import Incident
from app.notifications.incident_notifications import IncidentNotificationService
from app.repositories.incident import IncidentRepository
from app.repositories.sla import EscalationRepository, SlaRepository
from app.services.escalation import EscalationService

logger = get_logger("app.workers.escalation_sweep")


class EscalationSweepWorker:
    """Sweeps every organization's open incidents for due escalations."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        max_per_tick: int = 500,
        max_levels: int = 5,
    ) -> None:
        self._session_factory = session_factory
        self._max_per_tick = max_per_tick
        self._max_levels = max_levels

    async def run_job(self, _job: Job) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Sweep every organization; returns how many escalations fired."""
        organizations = await self._organizations()
        fired = 0
        for organization_id in organizations:
            fired += await self._sweep(organization_id)
        logger.info(
            "Escalation sweep complete.",
            extra={"extra_fields": {"organizations": len(organizations), "fired": fired}},
        )
        return fired

    async def _organizations(self) -> list[UUID]:
        """Every organization with at least one incident."""
        async with self._session_factory() as session:
            statement = select(distinct(Incident.organization_id)).limit(self._max_per_tick)
            result = await session.execute(statement)
            return [row for row in result.scalars().all() if row is not None]

    async def _sweep(self, organization_id: UUID) -> int:
        """Sweep one organization's open incidents under its own session."""
        try:
            async with self._session_factory() as session:
                incidents = IncidentRepository(session)
                notifications = IncidentNotificationService(create_notification_framework())
                service = EscalationService(
                    EscalationRepository(session),
                    SlaRepository(session),
                    incidents,
                    notifications,
                    max_levels=self._max_levels,
                )
                fired = 0
                for incident in await incidents.list_open(organization_id):
                    escalations = await service.evaluate_incident(
                        organization_id,
                        incident.id,
                        priority=incident_priority_of(incident.priority),
                    )
                    fired += len(escalations)
                await session.commit()
            return fired
        except Exception as exc:
            logger.warning(
                "An escalation sweep failed for one organization; the rest of the tick continues.",
                extra={
                    "extra_fields": {"organization_id": str(organization_id), "error": str(exc)}
                },
            )
            return 0


__all__ = ["EscalationSweepWorker"]
