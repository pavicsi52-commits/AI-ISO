"""Which managed assets a configuration profile targets.

Per docs/039's own "Target Assets"/``ConfigurationAssigned`` naming.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError

from app.events.configuration_events import ConfigurationAssignedEvent
from app.models.configuration_assignment import ConfigurationAssignment
from app.models.enums import ConfigurationAssignmentStatus
from app.repositories.configuration_assignment import ConfigurationAssignmentRepository
from app.repositories.configuration_profile import ConfigurationProfileRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class ConfigurationAssignmentService:
    """Assigns configuration profiles to managed assets and tracks status."""

    def __init__(
        self,
        assignments: ConfigurationAssignmentRepository,
        profiles: ConfigurationProfileRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._assignments = assignments
        self._profiles = profiles
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationAssignment]:
        """Every managed asset assigned to *profile_id*."""
        return await self._assignments.list_for_profile(profile_id)

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[ConfigurationAssignment]:
        """Every configuration profile assigned to *managed_asset_id*."""
        return await self._assignments.list_for_managed_asset(managed_asset_id)

    async def assign(
        self, profile_id: UUID, *, managed_asset_id: UUID, assigned_by: UUID | None
    ) -> ConfigurationAssignment:
        """Target *managed_asset_id* with *profile_id* ("Target Assets").

        Raises:
            ConflictError: If this profile/asset pair is already assigned.
        """
        existing = await self._assignments.get_for_profile_and_asset(profile_id, managed_asset_id)
        if existing is not None:
            raise ConflictError(
                f"Managed asset {managed_asset_id} is already assigned to profile {profile_id}."
            )
        profile = await self._profiles.require_by_id(profile_id)
        assignment = await self._assignments.create(
            ConfigurationAssignment(
                organization_id=profile.organization_id,
                profile_id=profile_id,
                managed_asset_id=managed_asset_id,
                status=ConfigurationAssignmentStatus.PENDING,
                assigned_by=assigned_by,
                assigned_at=datetime.now(UTC),
            )
        )
        await self._publish(
            ConfigurationAssignedEvent(
                source_service="configuration-management-service",
                payload={
                    "profile_id": str(profile_id),
                    "managed_asset_id": str(managed_asset_id),
                },
            )
        )
        return assignment

    async def set_status(
        self, assignment_id: UUID, status: ConfigurationAssignmentStatus
    ) -> ConfigurationAssignment:
        """Transition an assignment's deployment status."""
        assignment = await self._assignments.require_by_id(assignment_id)
        assignment.status = status
        return await self._assignments.update(assignment)

    async def unassign(self, assignment_id: UUID) -> None:
        """Remove an assignment ("Delete")."""
        await self._assignments.delete(assignment_id)


__all__ = ["ConfigurationAssignmentService"]
