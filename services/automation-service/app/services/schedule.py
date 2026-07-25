"""Recurring cron schedules for automation jobs. Per docs/040 "EXECUTION
MODES" "Scheduled". Building the actual ``shared_core.scheduler`` job
from an enabled row is :func:`app.scheduling.scheduler_integration
.build_scheduler_job`; this service only owns the row's own CRUD and
enable/disable lifecycle.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.models.automation_schedule import AutomationSchedule
from app.repositories.automation_schedule import AutomationScheduleRepository


class AutomationScheduleService:
    """Creates, reads, updates, and deletes automation job schedules."""

    def __init__(self, schedules: AutomationScheduleRepository) -> None:
        self._schedules = schedules

    async def get_by_id(self, schedule_id: UUID) -> AutomationSchedule:
        """Return the schedule identified by *schedule_id*.

        Raises:
            NotFoundError: If no such schedule exists.
        """
        return await self._schedules.require_by_id(schedule_id)

    async def list_for_job(self, job_id: UUID) -> list[AutomationSchedule]:
        """Every schedule recorded for *job_id*."""
        return await self._schedules.list_for_job(job_id)

    async def list_enabled_for_org(self, organization_id: UUID) -> list[AutomationSchedule]:
        """Every enabled schedule for *organization_id* (what the
        scheduler process loads at startup).
        """
        return await self._schedules.list_enabled_for_org(organization_id)

    async def create(
        self,
        job_id: UUID,
        *,
        organization_id: UUID,
        cron_expression: str,
        enabled: bool,
    ) -> AutomationSchedule:
        """Define a new recurring schedule for a job."""
        return await self._schedules.create(
            AutomationSchedule(
                organization_id=organization_id,
                job_id=job_id,
                cron_expression=cron_expression,
                enabled=enabled,
            )
        )

    async def set_enabled(self, schedule_id: UUID, *, enabled: bool) -> AutomationSchedule:
        """Enable or disable a schedule without deleting it."""
        schedule = await self.get_by_id(schedule_id)
        schedule.enabled = enabled
        return await self._schedules.update(schedule)

    async def record_run(
        self, schedule_id: UUID, *, ran_at: datetime, next_run_at: datetime | None
    ) -> AutomationSchedule:
        """Record that a schedule just fired, and when it fires next."""
        schedule = await self.get_by_id(schedule_id)
        schedule.last_run_at = ran_at
        schedule.next_run_at = next_run_at
        return await self._schedules.update(schedule)

    async def delete(self, schedule_id: UUID) -> None:
        """Soft-delete a schedule."""
        await self._schedules.delete(schedule_id)


__all__ = ["AutomationScheduleService"]
