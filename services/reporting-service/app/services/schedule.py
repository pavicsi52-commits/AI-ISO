"""Report scheduling ("SCHEDULING").

Owns the schedule rows and the "which are due?" question. Actually
*running* a due schedule belongs to :mod:`app.workers.scheduler`, so
this service stays free of rendering concerns and is directly testable
without a renderer.

**Retry is bounded and failures are visible.** A schedule that fails
``max_retries`` consecutive times is disabled rather than retried
forever: an unreachable data source would otherwise generate a failed
execution every minute indefinitely, burying real failures.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.logging.logger import get_logger

from app.events.report_events import SOURCE_SERVICE, ReportScheduledEvent
from app.models.enums import ExportFormat, ScheduleFrequency
from app.models.report_schedule import ReportSchedule
from app.repositories.report_schedule import ReportScheduleRepository
from app.scheduler.recurrence import compute_next_run, validate_schedule
from app.types import EventPublisher

logger = get_logger("app.services.schedule")


class ReportScheduleService:
    """Creates, updates, and advances report schedules."""

    def __init__(
        self, schedules: ReportScheduleRepository, *, publish_event: EventPublisher
    ) -> None:
        self._schedules = schedules
        self._publish_event = publish_event

    async def get_by_id(self, schedule_id: UUID) -> ReportSchedule:
        """Return one schedule.

        Raises:
            NotFoundError: If no such schedule exists.
        """
        return await self._schedules.require_by_id(schedule_id)

    async def list_for_job(self, job_id: UUID) -> list[ReportSchedule]:
        """Every schedule attached to one report."""
        return await self._schedules.list_for_job(job_id)

    async def list_for_org(self, organization_id: UUID) -> list[ReportSchedule]:
        """Every schedule for an organization."""
        return await self._schedules.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        job_id: UUID,
        frequency: ScheduleFrequency,
        starts_at: datetime,
        cron_expression: str | None = None,
        timezone_name: str = "UTC",
        export_format: ExportFormat = ExportFormat.PDF,
        ends_at: datetime | None = None,
        max_retries: int = 3,
        notify_on_failure: bool = True,
    ) -> ReportSchedule:
        """Create a schedule and compute its first run.

        Raises:
            ValidationError: If the frequency, cron expression, or time
                zone is invalid.
        """
        validate_schedule(frequency, cron_expression, timezone_name)
        next_run = compute_next_run(
            frequency,
            timezone_name=timezone_name,
            cron_expression=cron_expression,
            starts_at=starts_at,
        )
        schedule = await self._schedules.create(
            ReportSchedule(
                organization_id=organization_id,
                project_id=project_id,
                job_id=job_id,
                frequency=frequency,
                cron_expression=cron_expression,
                timezone=timezone_name,
                export_format=export_format,
                starts_at=starts_at,
                ends_at=ends_at,
                next_run_at=next_run,
                max_retries=max_retries,
                notify_on_failure=notify_on_failure,
            )
        )
        await self._publish_event(
            ReportScheduledEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "schedule_id": str(schedule.id),
                    "job_id": str(job_id),
                    "frequency": str(frequency),
                    "next_run_at": next_run.isoformat() if next_run else None,
                },
            )
        )
        return schedule

    async def update(
        self,
        schedule_id: UUID,
        *,
        frequency: ScheduleFrequency | None = None,
        cron_expression: str | None = None,
        timezone_name: str | None = None,
        export_format: ExportFormat | None = None,
        ends_at: datetime | None = None,
        enabled: bool | None = None,
    ) -> ReportSchedule:
        """Update a schedule, recomputing its next run.

        Any change to cadence recomputes ``next_run_at`` immediately,
        so an edited schedule cannot keep firing on its old cadence
        until the next tick happens to notice.

        Raises:
            NotFoundError: If no such schedule exists.
            ValidationError: If the resulting configuration is invalid.
        """
        schedule = await self._schedules.require_by_id(schedule_id)
        cadence_changed = False

        if frequency is not None:
            schedule.frequency = frequency
            cadence_changed = True
        if cron_expression is not None:
            schedule.cron_expression = cron_expression or None
            cadence_changed = True
        if timezone_name is not None:
            schedule.timezone = timezone_name
            cadence_changed = True
        if export_format is not None:
            schedule.export_format = export_format
        if ends_at is not None:
            schedule.ends_at = ends_at
        if enabled is not None:
            schedule.enabled = enabled
            if enabled:
                # Re-enabling clears the failure streak that disabled it,
                # otherwise one more failure would immediately re-disable.
                schedule.consecutive_failures = 0
                cadence_changed = True

        if cadence_changed:
            current = (
                schedule.frequency
                if isinstance(schedule.frequency, ScheduleFrequency)
                else ScheduleFrequency(schedule.frequency)
            )
            validate_schedule(current, schedule.cron_expression, schedule.timezone)
            schedule.next_run_at = compute_next_run(
                current,
                timezone_name=schedule.timezone,
                cron_expression=schedule.cron_expression,
                starts_at=schedule.starts_at,
            )
        return await self._schedules.update(schedule)

    async def delete(self, schedule_id: UUID, *, deleted_by: UUID | None = None) -> None:
        """Remove a schedule.

        Raises:
            NotFoundError: If no such schedule exists.
        """
        await self._schedules.require_by_id(schedule_id)
        await self._schedules.delete(schedule_id, deleted_by=deleted_by)

    async def list_due(
        self, *, moment: datetime | None = None, limit: int = 100
    ) -> list[ReportSchedule]:
        """Enabled schedules whose next run has arrived."""
        return await self._schedules.list_due(moment or datetime.now(UTC), limit=limit)

    async def mark_succeeded(self, schedule: ReportSchedule) -> ReportSchedule:
        """Record a successful run and advance to the next occurrence."""
        now = datetime.now(UTC)
        schedule.last_run_at = now
        schedule.consecutive_failures = 0
        schedule.last_error = None
        schedule.next_run_at = self._advance(schedule, after=now)
        return await self._schedules.update(schedule)

    async def mark_failed(self, schedule: ReportSchedule, reason: str) -> ReportSchedule:
        """Record a failed run, disabling the schedule if it keeps failing."""
        now = datetime.now(UTC)
        schedule.last_run_at = now
        schedule.consecutive_failures += 1
        schedule.last_error = reason[:1000]

        if schedule.consecutive_failures >= schedule.max_retries:
            schedule.enabled = False
            schedule.next_run_at = None
            logger.warning(
                "Report schedule disabled after repeated failures.",
                extra={
                    "extra_fields": {
                        "schedule_id": str(schedule.id),
                        "failures": schedule.consecutive_failures,
                    }
                },
            )
        else:
            schedule.next_run_at = self._advance(schedule, after=now)
        return await self._schedules.update(schedule)

    def _advance(self, schedule: ReportSchedule, *, after: datetime) -> datetime | None:
        """The next run instant after *after*, or ``None`` if finished."""
        frequency = (
            schedule.frequency
            if isinstance(schedule.frequency, ScheduleFrequency)
            else ScheduleFrequency(schedule.frequency)
        )
        if frequency is ScheduleFrequency.ONE_TIME:
            return None
        return compute_next_run(
            frequency,
            timezone_name=schedule.timezone,
            cron_expression=schedule.cron_expression,
            starts_at=schedule.starts_at,
            after=after,
        )


__all__ = ["ReportScheduleService"]
