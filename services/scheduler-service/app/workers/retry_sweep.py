"""The retry sweep worker.

Dispatches the next attempt for every non-terminal failure whose own
``retry_at`` has arrived. **Leader-elected** through
``shared_core.scheduler`` -- see :mod:`app.workers.registrar`. **One
session per organization**, so a failure sweeping one tenant's retries
does not poison the transaction the next tenant's sweep needs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.notifications.factory import create_notification_framework
from shared_core.scheduler import Job
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.history import JobFailure
from app.notifications.scheduler_notifications import SchedulerNotificationService
from app.repositories.execution import JobExecutionLogRepository, JobExecutionRepository
from app.repositories.history import JobFailureRepository, JobHistoryRepository
from app.repositories.job import ScheduledJobRepository
from app.repositories.retry import JobRetryPolicyRepository
from app.services.execution import ExecutionService
from app.services.job import JobService

logger = get_logger("app.workers.retry_sweep")


class RetrySweepWorker:
    """Dispatches every failure whose retry delay has elapsed."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], *, max_per_tick: int = 500
    ) -> None:
        self._session_factory = session_factory
        self._max_per_tick = max_per_tick

    async def run_job(self, _job: Job) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Sweep every organization; returns how many retries were dispatched."""
        organizations = await self._organizations()
        retried = 0
        for organization_id in organizations:
            retried += await self._sweep(organization_id)
        logger.info(
            "Retry sweep complete.",
            extra={"extra_fields": {"organizations": len(organizations), "retried": retried}},
        )
        return retried

    async def _organizations(self) -> list[UUID]:
        """Every organization with at least one failure."""
        async with self._session_factory() as session:
            statement = select(distinct(JobFailure.organization_id)).limit(self._max_per_tick)
            result = await session.execute(statement)
            return [row for row in result.scalars().all() if row is not None]

    async def _sweep(self, organization_id: UUID) -> int:
        """Sweep one organization's due retries under its own session."""
        try:
            async with self._session_factory() as session:
                failures = JobFailureRepository(session)
                due = await failures.list_due_for_retry(organization_id, before=datetime.now(UTC))

                notifications = SchedulerNotificationService(create_notification_framework())
                job_service = JobService(
                    ScheduledJobRepository(session), JobHistoryRepository(session)
                )
                execution_service = ExecutionService(
                    JobExecutionRepository(session),
                    JobExecutionLogRepository(session),
                    failures,
                    ScheduledJobRepository(session),
                    JobRetryPolicyRepository(session),
                    job_service,
                    notifications,
                )

                for failure in due:
                    await execution_service.retry_failure(organization_id, failure.id)
                await session.commit()
            return len(due)
        except Exception as exc:
            logger.warning(
                "A retry sweep failed for one organization; the rest of the tick continues.",
                extra={
                    "extra_fields": {"organization_id": str(organization_id), "error": str(exc)}
                },
            )
            return 0


__all__ = ["RetrySweepWorker"]
