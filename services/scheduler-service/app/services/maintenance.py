"""Maintenance windows: creating them, and checking whether dispatch is currently suppressed."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.events.scheduler_events import SOURCE_SERVICE, MaintenanceStartedEvent
from app.models.enums import (
    CalendarRuleKind,
    JobPriority,
    MaintenanceWindowKind,
    MaintenanceWindowScope,
)
from app.models.maintenance import MaintenanceWindow
from app.repositories.maintenance import MaintenanceWindowRepository
from app.scheduling.engine import is_dispatch_suppressed
from app.types import EventPublisher


class MaintenanceWindowService:
    """Maintenance windows, and the dispatch-suppression decision they drive."""

    def __init__(
        self, windows: MaintenanceWindowRepository, *, publish_event: EventPublisher | None = None
    ) -> None:
        self._windows = windows
        self._publish = publish_event

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def create_window(
        self,
        organization_id: UUID,
        *,
        title: str,
        starts_at: datetime,
        ends_at: datetime,
        scope: MaintenanceWindowScope = MaintenanceWindowScope.ORGANIZATION,
        scope_id: str | None = None,
        kind: MaintenanceWindowKind = MaintenanceWindowKind.STANDARD,
        description: str | None = None,
        timezone: str = "UTC",
        recurrence: CalendarRuleKind = CalendarRuleKind.NONE,
        recurrence_until: datetime | None = None,
        allow_critical_override: bool = False,
    ) -> MaintenanceWindow:
        """Define a maintenance window.

        Raises:
            ValidationError: If *ends_at* is not after *starts_at*.
        """
        if ends_at <= starts_at:
            raise ValidationError("A maintenance window must end after it starts.")
        created = await self._windows.create(
            MaintenanceWindow(
                organization_id=organization_id,
                scope=scope,
                scope_id=scope_id,
                kind=kind,
                title=title,
                description=description,
                starts_at=starts_at,
                ends_at=ends_at,
                timezone=timezone,
                recurrence=recurrence,
                recurrence_until=recurrence_until,
                allow_critical_override=allow_critical_override,
            )
        )
        moment = datetime.now(UTC)
        if created.starts_at <= moment < created.ends_at:
            await self._publish_event(
                MaintenanceStartedEvent(
                    source_service=SOURCE_SERVICE,
                    payload={
                        "organization_id": str(organization_id),
                        "window_id": str(created.id),
                        "title": created.title,
                    },
                )
            )
        return created

    async def get(self, organization_id: UUID, window_id: UUID) -> MaintenanceWindow:
        """One window.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._windows.require_in_org(organization_id, window_id)

    async def list_windows(
        self, organization_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[MaintenanceWindow]:
        """Every window this organization has defined, soonest first."""
        return await self._windows.list_for_org(organization_id, limit=limit, offset=offset)

    async def active_windows(
        self, organization_id: UUID, *, moment: datetime | None = None
    ) -> list[MaintenanceWindow]:
        """Every window currently active."""
        return await self._windows.list_active_at(
            organization_id, moment=moment or datetime.now(UTC)
        )

    async def is_dispatch_suppressed_for(
        self, organization_id: UUID, *, priority: JobPriority, moment: datetime | None = None
    ) -> bool:
        """Whether at least one active window currently blocks dispatch at *priority*."""
        active = await self.active_windows(organization_id, moment=moment)
        overrides = {str(one.id): one.allow_critical_override for one in active}
        return is_dispatch_suppressed(priority=priority, active_window_allows_override=overrides)


__all__ = ["MaintenanceWindowService"]
