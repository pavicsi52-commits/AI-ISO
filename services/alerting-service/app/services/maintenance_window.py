"""Maintenance window CRUD ("MAINTENANCE WINDOWS")."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.alert_maintenance_window import AlertMaintenanceWindow
from app.models.enums import MaintenanceWindowScope, MaintenanceWindowType
from app.repositories.alert_maintenance_window import AlertMaintenanceWindowRepository
from app.suppression.maintenance import is_window_active


class AlertMaintenanceWindowService:
    """Creates and reads maintenance windows."""

    def __init__(self, windows: AlertMaintenanceWindowRepository) -> None:
        self._windows = windows

    async def get_by_id(self, window_id: UUID) -> AlertMaintenanceWindow:
        """Return the window identified by *window_id*.

        Raises:
            NotFoundError: If no such window exists.
        """
        return await self._windows.require_by_id(window_id)

    async def list_for_org(self, organization_id: UUID) -> list[AlertMaintenanceWindow]:
        """Every maintenance window belonging to *organization_id*."""
        return await self._windows.list_for_org(organization_id)

    async def list_active(
        self, organization_id: UUID, *, moment: datetime | None = None
    ) -> list[AlertMaintenanceWindow]:
        """Every window actually in force at *moment*, recurrence included."""
        now = moment or datetime.now(UTC)
        enabled = await self._windows.list_enabled_for_org(organization_id)
        return [window for window in enabled if is_window_active(window, now)]

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        name: str,
        window_type: MaintenanceWindowType,
        scope: MaintenanceWindowScope,
        scope_reference: str | None,
        recurrence_rule: str | None,
        starts_at: datetime,
        ends_at: datetime,
        enabled: bool,
    ) -> AlertMaintenanceWindow:
        """Create a maintenance window."""
        return await self._windows.create(
            AlertMaintenanceWindow(
                organization_id=organization_id,
                project_id=project_id,
                name=name,
                window_type=window_type,
                scope=scope,
                scope_reference=scope_reference,
                recurrence_rule=recurrence_rule,
                starts_at=starts_at,
                ends_at=ends_at,
                enabled=enabled,
            )
        )


__all__ = ["AlertMaintenanceWindowService"]
