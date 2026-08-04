"""The due-schedule sweep worker.

Dispatches every job whose materialized :class:`~app.models.trigger.JobSchedule`
has become due, then recomputes each one's next due time. **Leader-elected**
through ``shared_core.scheduler`` -- see :mod:`app.workers.registrar`.

**Dependency-driven triggers are deliberately not polled here.** A
``DEPENDENCY_DRIVEN`` trigger's own next-due computation is always
``None`` (see ``app.scheduling.engine.compute_next_run_at``), so it never
appears in :meth:`~app.repositories.trigger.JobScheduleRepository
.list_due`. Blindly re-checking every dependency-driven job's readiness
on every tick with no dedup marker would risk dispatching it repeatedly
for as long as its parent stays in a satisfying status -- out of scope
for this sweep; dispatching a dependency-driven job today happens
through ``POST /scheduler/jobs/{id}/run`` once a caller has confirmed
readiness via ``GET .../dependencies``.

**One session per organization.** A failure sweeping one tenant's
schedules must not poison the transaction the next tenant's sweep needs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from shared_core.logging.logger import get_logger
from shared_core.notifications.factory import create_notification_framework
from shared_core.scheduler import Job
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.enums import ScheduledJobStatus, scheduled_job_status_of
from app.models.job import ScheduledJob
from app.notifications.scheduler_notifications import SchedulerNotificationService
from app.repositories.execution import JobExecutionLogRepository, JobExecutionRepository
from app.repositories.history import JobFailureRepository, JobHistoryRepository
from app.repositories.holiday import HolidayCalendarRepository
from app.repositories.job import ScheduledJobRepository
from app.repositories.maintenance import MaintenanceWindowRepository
from app.repositories.retry import JobRetryPolicyRepository
from app.repositories.trigger import JobScheduleRepository, JobTriggerRepository
from app.scheduling.engine import is_dispatch_suppressed
from app.services.execution import ExecutionService
from app.services.job import JobService
from app.services.trigger import TriggerService

logger = get_logger("app.workers.due_schedule_sweep")


class DueScheduleSweepWorker:
    """Dispatches every job schedule that has become due."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        max_per_tick: int = 500,
        lookahead_seconds: int = 60,
    ) -> None:
        self._session_factory = session_factory
        self._max_per_tick = max_per_tick
        self._lookahead_seconds = lookahead_seconds

    async def run_job(self, _job: Job) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> dict[str, int]:
        """Sweep every organization; returns aggregate dispatch/skip counts."""
        organizations = await self._organizations()
        dispatched = suppressed = 0
        for organization_id in organizations:
            counts = await self._sweep(organization_id)
            dispatched += counts["dispatched"]
            suppressed += counts["suppressed"]
        logger.info(
            "Due-schedule sweep complete.",
            extra={
                "extra_fields": {
                    "organizations": len(organizations),
                    "dispatched": dispatched,
                    "suppressed": suppressed,
                }
            },
        )
        return {
            "organizations": len(organizations),
            "dispatched": dispatched,
            "suppressed": suppressed,
        }

    async def _organizations(self) -> list[UUID]:
        """Every organization with at least one job."""
        async with self._session_factory() as session:
            statement = select(distinct(ScheduledJob.organization_id)).limit(self._max_per_tick)
            result = await session.execute(statement)
            return [row for row in result.scalars().all() if row is not None]

    async def _sweep(self, organization_id: UUID) -> dict[str, int]:
        """Sweep one organization's due schedules under its own session."""
        try:
            async with self._session_factory() as session:
                now = datetime.now(UTC)
                horizon = now + timedelta(seconds=self._lookahead_seconds)
                schedules = JobScheduleRepository(session)
                due = await schedules.list_due(organization_id, before=horizon)

                notifications = SchedulerNotificationService(create_notification_framework())
                job_service = JobService(
                    ScheduledJobRepository(session), JobHistoryRepository(session)
                )
                execution_service = ExecutionService(
                    JobExecutionRepository(session),
                    JobExecutionLogRepository(session),
                    JobFailureRepository(session),
                    ScheduledJobRepository(session),
                    JobRetryPolicyRepository(session),
                    job_service,
                    notifications,
                )
                trigger_service = TriggerService(
                    JobTriggerRepository(session),
                    schedules,
                    ScheduledJobRepository(session),
                    HolidayCalendarRepository(session),
                )
                windows = MaintenanceWindowRepository(session)

                dispatched = suppressed = 0
                for schedule in due:
                    job = await ScheduledJobRepository(session).require_in_org(
                        organization_id, schedule.job_id
                    )
                    if scheduled_job_status_of(job.status) is not ScheduledJobStatus.ACTIVE:
                        continue

                    active = await windows.list_active_at(organization_id, moment=now)
                    overrides = {str(one.id): one.allow_critical_override for one in active}
                    if is_dispatch_suppressed(
                        priority=job.priority, active_window_allows_override=overrides
                    ):
                        suppressed += 1
                        continue

                    await execution_service.dispatch(
                        organization_id, job.id, trigger_source="schedule"
                    )
                    await trigger_service.recompute_schedule(organization_id, job.id, now=now)
                    dispatched += 1
                await session.commit()
            return {"dispatched": dispatched, "suppressed": suppressed}
        except Exception as exc:
            logger.warning(
                "A due-schedule sweep failed for one organization; the rest of the tick continues.",
                extra={
                    "extra_fields": {"organization_id": str(organization_id), "error": str(exc)}
                },
            )
            return {"dispatched": 0, "suppressed": 0}


__all__ = ["DueScheduleSweepWorker"]
