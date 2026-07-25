"""Discovery schedule management. Per docs/037 "SCHEDULING"."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.models.discovery_schedule import DiscoverySchedule
from app.models.enums import ScheduleType
from app.repositories.discovery_schedule import DiscoveryScheduleRepository


class DiscoveryScheduleService:
    """Creates, updates, and lists discovery schedules."""

    def __init__(self, schedules: DiscoveryScheduleRepository) -> None:
        self._schedules = schedules

    async def get_by_id(self, schedule_id: UUID) -> DiscoverySchedule:
        """Return the schedule identified by *schedule_id*.

        Raises:
            NotFoundError: If no such schedule exists.
        """
        return await self._schedules.require_by_id(schedule_id)

    async def list_for_org(self, organization_id: UUID) -> list[DiscoverySchedule]:
        """Every schedule defined for *organization_id*."""
        return await self._schedules.list_for_org(organization_id)

    async def list_due(self, *, as_of: datetime) -> list[DiscoverySchedule]:
        """Every active schedule whose ``next_run_at`` has arrived."""
        return await self._schedules.list_due(as_of=as_of)

    async def list_active(self) -> list[DiscoverySchedule]:
        """Every active schedule across every organization ("Job
        Registration" at startup -- see
        ``app/core/factory.py``'s ``_lifespan``).
        """
        return await self._schedules.list_active()

    async def create(
        self,
        *,
        organization_id: UUID,
        profile_id: UUID,
        name: str,
        schedule_type: ScheduleType,
        cron_expression: str | None,
        interval_seconds: int | None,
        next_run_at: datetime | None,
        maintenance_window: dict[str, Any],
        retry_policy: dict[str, Any],
        priority: int,
        concurrency_limit: int,
    ) -> DiscoverySchedule:
        """Create a new discovery schedule."""
        return await self._schedules.create(
            DiscoverySchedule(
                organization_id=organization_id,
                profile_id=profile_id,
                name=name,
                schedule_type=schedule_type,
                cron_expression=cron_expression,
                interval_seconds=interval_seconds,
                next_run_at=next_run_at,
                maintenance_window=maintenance_window,
                retry_policy=retry_policy,
                priority=priority,
                concurrency_limit=concurrency_limit,
            )
        )

    async def update(
        self,
        schedule_id: UUID,
        *,
        name: str,
        schedule_type: ScheduleType,
        cron_expression: str | None,
        interval_seconds: int | None,
        next_run_at: datetime | None,
        is_enabled: bool,
        maintenance_window: dict[str, Any],
        retry_policy: dict[str, Any],
        priority: int,
        concurrency_limit: int,
    ) -> DiscoverySchedule:
        """Replace a schedule's mutable fields.

        Raises:
            NotFoundError: If no such schedule exists.
        """
        schedule = await self.get_by_id(schedule_id)
        schedule.name = name
        schedule.schedule_type = schedule_type
        schedule.cron_expression = cron_expression
        schedule.interval_seconds = interval_seconds
        schedule.next_run_at = next_run_at
        schedule.is_enabled = is_enabled
        schedule.maintenance_window = maintenance_window
        schedule.retry_policy = retry_policy
        schedule.priority = priority
        schedule.concurrency_limit = concurrency_limit
        return schedule

    async def record_run(self, schedule_id: UUID, *, ran_at: datetime) -> DiscoverySchedule:
        """Record that *schedule_id* fired at *ran_at*."""
        schedule = await self.get_by_id(schedule_id)
        schedule.last_run_at = ran_at
        return schedule

    async def delete(self, schedule_id: UUID) -> None:
        """Delete a schedule.

        Raises:
            NotFoundError: If no such schedule exists.
        """
        await self._schedules.delete(schedule_id)


__all__ = ["DiscoveryScheduleService"]
