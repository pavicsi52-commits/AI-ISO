"""On-call schedule CRUD plus current-on-call resolution."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.escalation.oncall import resolve_oncall
from app.models.alert_oncall_schedule import AlertOnCallSchedule
from app.models.enums import OnCallRotationType
from app.repositories.alert_oncall_schedule import AlertOnCallScheduleRepository


class AlertOnCallScheduleService:
    """Creates and reads on-call schedules, and resolves who is on call."""

    def __init__(self, schedules: AlertOnCallScheduleRepository) -> None:
        self._schedules = schedules

    async def get_by_id(self, schedule_id: UUID) -> AlertOnCallSchedule:
        """Return the schedule identified by *schedule_id*.

        Raises:
            NotFoundError: If no such schedule exists.
        """
        return await self._schedules.require_by_id(schedule_id)

    async def list_for_org(self, organization_id: UUID) -> list[AlertOnCallSchedule]:
        """Every on-call schedule belonging to *organization_id*."""
        return await self._schedules.list_for_org(organization_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        name: str,
        rotation_type: OnCallRotationType,
        timezone: str,
        participants: list[str],
        overrides: list[dict[str, Any]],
        holiday_calendar: list[str],
        enabled: bool,
    ) -> AlertOnCallSchedule:
        """Create an on-call schedule."""
        return await self._schedules.create(
            AlertOnCallSchedule(
                organization_id=organization_id,
                project_id=project_id,
                name=name,
                rotation_type=rotation_type,
                timezone=timezone,
                participants=participants,
                overrides=overrides,
                holiday_calendar=holiday_calendar,
                enabled=enabled,
            )
        )

    async def current_oncall(
        self, schedule_id: UUID, *, moment: datetime | None = None
    ) -> str | None:
        """Return the user id on call for *schedule_id*, or ``None``.

        Raises:
            NotFoundError: If no such schedule exists.
        """
        schedule = await self._schedules.require_by_id(schedule_id)
        return resolve_oncall(schedule, moment or datetime.now(UTC))


__all__ = ["AlertOnCallScheduleService"]
