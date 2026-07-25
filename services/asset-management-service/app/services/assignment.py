"""Asset assignment management. Per docs/038 "ASSIGNMENTS" "Support":
Assign Asset, Reassign Asset, Bulk Assignment, Assignment History,
Assignment Approval, Temporary Assignment.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.asset_events import AssetAssignedEvent
from app.models.asset_assignment import AssetAssignment
from app.models.enums import AssignmentStatus, AssignmentType
from app.repositories.asset_assignment import AssetAssignmentRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class AssetAssignmentService:
    """Assigns, reassigns, and lists assignments for a managed asset."""

    def __init__(
        self,
        assignments: AssetAssignmentRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._assignments = assignments
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetAssignment]:
        """Every assignment recorded for *managed_asset_id* ("Assignment History")."""
        return await self._assignments.list_for_managed_asset(managed_asset_id)

    async def assign(
        self,
        managed_asset_id: UUID,
        *,
        organization_id: UUID,
        assignee_id: UUID,
        assignment_type: AssignmentType,
        assigned_by: UUID | None,
        expires_at: datetime | None,
        notes: str | None,
    ) -> AssetAssignment:
        """Assign (or reassign) *managed_asset_id* to *assignee_id*
        ("Assign Asset"/"Reassign Asset"/"Temporary Assignment") --
        returning any prior active assignment first.
        """
        now = datetime.now(UTC)
        active = await self._assignments.get_active_for_managed_asset(managed_asset_id)
        if active is not None:
            active.status = AssignmentStatus.RETURNED
            active.returned_at = now

        assignment = await self._assignments.create(
            AssetAssignment(
                managed_asset_id=managed_asset_id,
                organization_id=organization_id,
                assignee_id=assignee_id,
                assignment_type=assignment_type,
                status=AssignmentStatus.ACTIVE,
                assigned_by=assigned_by,
                assigned_at=now,
                expires_at=expires_at,
                notes=notes,
            )
        )
        await self._publish(
            AssetAssignedEvent(
                source_service="asset-management-service",
                payload={
                    "managed_asset_id": str(managed_asset_id),
                    "assignee_id": str(assignee_id),
                },
            )
        )
        return assignment


__all__ = ["AssetAssignmentService"]
