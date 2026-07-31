"""The maintenance sweep worker.

Two jobs whose absence is silent, which is why they are swept rather
than left to be noticed:

1. **Lapsed exceptions.** A waiver past its expiry that is still marked
   ``ACTIVE`` goes on waiving a control it no longer covers -- and every
   assessment in between reports ``EXCEPTED`` for a failure nobody has
   agreed to accept since the expiry date.
2. **Stuck assessments.** A ``RUNNING`` row left by a worker that died
   never clears itself, and while it stands it blocks the next scheduled
   run for that framework. The symptom is *nothing happening*, which is
   the hardest kind of failure to notice.

**Leader-elected** through ``shared_core.scheduler`` -- see
:mod:`app.workers.registrar`.

**One session per organization**, so a failure on one tenant does not
poison the transaction the next one needs.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.notifications.factory import create_notification_framework
from shared_core.scheduler import Job
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.framework import ComplianceFramework
from app.notifications.compliance_notifications import ComplianceNotificationService
from app.repositories.catalogue import ControlRepository, FrameworkRepository
from app.repositories.governance import ExceptionRepository
from app.repositories.runs import (
    AssessmentRepository,
    EvidenceRepository,
    ResultRepository,
)
from app.services.assessment import AssessmentService
from app.services.governance import ExceptionService

logger = get_logger("app.workers.maintenance")


class MaintenanceWorker:
    """Expires lapsed exceptions and reaps abandoned assessments."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        max_per_tick: int = 200,
        stuck_after_minutes: int = 60,
    ) -> None:
        self._session_factory = session_factory
        self._max_per_tick = max_per_tick
        self._stuck_after_minutes = stuck_after_minutes

    async def run_job(self, _job: Job) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> dict[str, int]:
        """Sweep every organization; returns what was cleaned up."""
        organizations = await self._organizations()
        expired = 0
        reaped = 0
        for organization_id in organizations:
            counts = await self._sweep(organization_id)
            expired += counts["expired"]
            reaped += counts["reaped"]
        logger.info(
            "Compliance maintenance sweep complete.",
            extra={
                "extra_fields": {
                    "organizations": len(organizations),
                    "exceptions_expired": expired,
                    "assessments_reaped": reaped,
                }
            },
        )
        return {"organizations": len(organizations), "expired": expired, "reaped": reaped}

    async def _organizations(self) -> list[UUID]:
        """Every organization with a compliance catalogue."""
        async with self._session_factory() as session:
            statement = (
                select(distinct(ComplianceFramework.organization_id))
                .where(ComplianceFramework.deleted_at.is_(None))
                .limit(self._max_per_tick)
            )
            result = await session.execute(statement)
            return [row for row in result.scalars().all() if row is not None]

    async def _sweep(self, organization_id: UUID) -> dict[str, int]:
        """Sweep one organization under its own session."""
        try:
            async with self._session_factory() as session:
                notifications = ComplianceNotificationService(create_notification_framework())
                exceptions = ExceptionService(
                    ExceptionRepository(session),
                    ControlRepository(session),
                    notifications,
                )
                assessments = AssessmentService(
                    AssessmentRepository(session),
                    ResultRepository(session),
                    ControlRepository(session),
                    FrameworkRepository(session),
                    ExceptionRepository(session),
                    EvidenceRepository(session),
                )
                expired = await exceptions.expire_lapsed(organization_id)
                reaped = await assessments.reap_stuck(
                    organization_id, older_than_minutes=self._stuck_after_minutes
                )
                await session.commit()
            return {"expired": expired, "reaped": len(reaped)}
        except Exception as exc:
            logger.warning(
                "A compliance maintenance sweep failed; the rest of the tick continues.",
                extra={
                    "extra_fields": {
                        "organization_id": str(organization_id),
                        "error": str(exc),
                    }
                },
            )
            return {"expired": 0, "reaped": 0}


__all__ = ["MaintenanceWorker"]
