"""Maintenance scheduling, windows, and history. Per docs/038
"MAINTENANCE" "Support": Scheduled, Emergency, Preventive, Corrective
Maintenance, Maintenance History, Maintenance Calendar, Approval
Workflow. Per docs/038 "MAINTENANCE WINDOWS" "Support": Recurring
Windows, One-Time Windows, Downtime Tracking, Approval, Notifications,
Execution History.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.events.base import DomainEvent
from shared_core.exceptions.validation import ValidationError

from app.events.asset_events import MaintenanceCompletedEvent, MaintenanceScheduledEvent
from app.models.asset_maintenance import AssetMaintenance
from app.models.asset_maintenance_history import AssetMaintenanceHistoryEntry
from app.models.asset_maintenance_window import AssetMaintenanceWindow
from app.models.enums import MaintenanceStatus, MaintenanceType, MaintenanceWindowType
from app.repositories.asset_maintenance import AssetMaintenanceRepository
from app.repositories.asset_maintenance_history import AssetMaintenanceHistoryRepository
from app.repositories.asset_maintenance_window import AssetMaintenanceWindowRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class MaintenanceService:
    """Schedules, approves, and completes maintenance for a managed asset."""

    def __init__(
        self,
        maintenance: AssetMaintenanceRepository,
        windows: AssetMaintenanceWindowRepository,
        history: AssetMaintenanceHistoryRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._maintenance = maintenance
        self._windows = windows
        self._history = history
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetMaintenance]:
        """Every maintenance activity for *managed_asset_id* ("Maintenance Calendar")."""
        return await self._maintenance.list_for_managed_asset(managed_asset_id)

    async def schedule(
        self,
        managed_asset_id: UUID,
        *,
        organization_id: UUID,
        maintenance_type: MaintenanceType,
        description: str,
        scheduled_at: datetime,
    ) -> AssetMaintenance:
        """Schedule a maintenance activity ("Scheduled"/"Emergency"/
        "Preventive"/"Corrective" Maintenance).
        """
        maintenance = await self._maintenance.create(
            AssetMaintenance(
                managed_asset_id=managed_asset_id,
                organization_id=organization_id,
                maintenance_type=maintenance_type,
                status=MaintenanceStatus.SCHEDULED,
                description=description,
                scheduled_at=scheduled_at,
            )
        )
        await self._record_history(
            managed_asset_id,
            organization_id=organization_id,
            maintenance_id=maintenance.id,
            event_type="scheduled",
            detail={"maintenance_type": str(maintenance_type)},
        )
        await self._publish(
            MaintenanceScheduledEvent(
                source_service="asset-management-service",
                payload={
                    "managed_asset_id": str(managed_asset_id),
                    "maintenance_id": str(maintenance.id),
                },
            )
        )
        return maintenance

    async def approve(self, maintenance_id: UUID, *, approved_by: UUID | None) -> AssetMaintenance:
        """Approve a scheduled maintenance activity ("Approval Workflow")."""
        maintenance = await self._maintenance.require_by_id(maintenance_id)
        maintenance.approved_by = approved_by
        maintenance.approved_at = datetime.now(UTC)
        return maintenance

    async def complete(self, maintenance_id: UUID, *, actor_id: UUID | None) -> AssetMaintenance:
        """Mark a maintenance activity completed."""
        maintenance = await self._maintenance.require_by_id(maintenance_id)
        maintenance.status = MaintenanceStatus.COMPLETED
        maintenance.completed_at = datetime.now(UTC)
        await self._record_history(
            maintenance.managed_asset_id,
            organization_id=maintenance.organization_id,
            maintenance_id=maintenance.id,
            event_type="completed",
            detail={},
        )
        await self._publish(
            MaintenanceCompletedEvent(
                source_service="asset-management-service",
                payload={
                    "managed_asset_id": str(maintenance.managed_asset_id),
                    "maintenance_id": str(maintenance_id),
                },
            )
        )
        return maintenance

    async def _record_history(
        self,
        managed_asset_id: UUID,
        *,
        organization_id: UUID,
        maintenance_id: UUID | None,
        event_type: str,
        detail: dict[str, Any],
    ) -> AssetMaintenanceHistoryEntry:
        return await self._history.create(
            AssetMaintenanceHistoryEntry(
                managed_asset_id=managed_asset_id,
                organization_id=organization_id,
                maintenance_id=maintenance_id,
                event_type=event_type,
                detail=detail,
                occurred_at=datetime.now(UTC),
            )
        )

    async def list_history(self, managed_asset_id: UUID) -> list[AssetMaintenanceHistoryEntry]:
        """Every maintenance timeline entry for *managed_asset_id* ("Execution History")."""
        return await self._history.list_for_managed_asset(managed_asset_id)

    async def list_windows(self, managed_asset_id: UUID) -> list[AssetMaintenanceWindow]:
        """Every maintenance window for *managed_asset_id*."""
        return await self._windows.list_for_managed_asset(managed_asset_id)

    async def create_window(
        self,
        managed_asset_id: UUID,
        *,
        organization_id: UUID,
        window_type: MaintenanceWindowType,
        starts_at: datetime,
        ends_at: datetime,
        recurrence_rule: str | None,
    ) -> AssetMaintenanceWindow:
        """Create a maintenance window ("Recurring Windows"/"One-Time Windows").

        Raises:
            ValidationError: If *ends_at* is not after *starts_at*.
        """
        if ends_at <= starts_at:
            raise ValidationError("A maintenance window must end after it starts.")
        return await self._windows.create(
            AssetMaintenanceWindow(
                managed_asset_id=managed_asset_id,
                organization_id=organization_id,
                window_type=window_type,
                starts_at=starts_at,
                ends_at=ends_at,
                recurrence_rule=recurrence_rule,
            )
        )


__all__ = ["MaintenanceService"]
