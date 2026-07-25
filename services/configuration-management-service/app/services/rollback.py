"""Roll a configuration profile back to a prior version.

Per docs/039 "ROLLBACK" "Support": Version Rollback, Incremental
Rollback, Full Rollback, Rollback Validation, Approval Workflow,
Rollback History. ``initiate`` publishes ``RollbackStarted`` and leaves
the rollback ``PENDING``; ``approve`` records who authorized it
("Approval Workflow"); ``complete`` applies :attr:`~app.models
.configuration_version.ConfigurationVersion.content` back onto the
profile and publishes ``RollbackCompleted``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.configuration_events import RollbackCompletedEvent, RollbackStartedEvent
from app.models.configuration_rollback import ConfigurationRollback
from app.models.enums import RollbackStatus, RollbackType
from app.repositories.configuration_profile import ConfigurationProfileRepository
from app.repositories.configuration_rollback import ConfigurationRollbackRepository
from app.services.version import ConfigurationVersionService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class ConfigurationRollbackService:
    """Initiates, approves, and completes configuration profile rollbacks."""

    def __init__(
        self,
        rollbacks: ConfigurationRollbackRepository,
        versions: ConfigurationVersionService,
        profiles: ConfigurationProfileRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._rollbacks = rollbacks
        self._versions = versions
        self._profiles = profiles
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, rollback_id: UUID) -> ConfigurationRollback:
        """Return the rollback identified by *rollback_id*.

        Raises:
            NotFoundError: If no such rollback exists.
        """
        return await self._rollbacks.require_by_id(rollback_id)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationRollback]:
        """Every rollback recorded for *profile_id*, newest first ("Rollback History")."""
        return await self._rollbacks.list_for_profile(profile_id)

    async def initiate(
        self,
        profile_id: UUID,
        *,
        to_version_id: UUID,
        rollback_type: RollbackType,
        requested_by: UUID | None,
        reason: str | None,
    ) -> ConfigurationRollback:
        """Request a rollback of *profile_id* to *to_version_id*
        ("Version Rollback"/"Full Rollback"), publishing ``RollbackStarted``.

        Raises:
            NotFoundError: If *to_version_id* does not exist.
        """
        to_version = await self._versions.get_by_id(to_version_id)
        from_version = await self._versions.get_latest_for_profile(
            profile_id, branch=to_version.branch
        )
        profile = await self._profiles.require_by_id(profile_id)
        rollback = await self._rollbacks.create(
            ConfigurationRollback(
                organization_id=profile.organization_id,
                profile_id=profile_id,
                from_version_id=from_version.id if from_version is not None else None,
                to_version_id=to_version_id,
                rollback_type=rollback_type,
                status=RollbackStatus.PENDING,
                requested_by=requested_by,
                reason=reason,
            )
        )
        await self._publish(
            RollbackStartedEvent(
                source_service="configuration-management-service",
                payload={"rollback_id": str(rollback.id), "profile_id": str(profile_id)},
            )
        )
        return rollback

    async def approve(self, rollback_id: UUID, *, approved_by: UUID) -> ConfigurationRollback:
        """Authorize a pending rollback ("Approval Workflow")."""
        rollback = await self.get_by_id(rollback_id)
        rollback.status = RollbackStatus.APPROVED
        rollback.approved_by = approved_by
        return await self._rollbacks.update(rollback)

    async def complete(self, rollback_id: UUID) -> ConfigurationRollback:
        """Apply the target version's content back onto the profile
        ("Version Rollback"), publishing ``RollbackCompleted``.
        """
        rollback = await self.get_by_id(rollback_id)
        rollback.status = RollbackStatus.IN_PROGRESS
        rollback = await self._rollbacks.update(rollback)

        to_version = await self._versions.get_by_id(rollback.to_version_id)
        profile = await self._profiles.require_by_id(rollback.profile_id)
        profile.variables = to_version.content.get("variables", {})
        profile.target_assets = to_version.content.get("target_assets", [])
        await self._profiles.update(profile)

        rollback.status = RollbackStatus.COMPLETED
        rollback.completed_at = datetime.now(UTC)
        rollback = await self._rollbacks.update(rollback)

        await self._publish(
            RollbackCompletedEvent(
                source_service="configuration-management-service",
                payload={"rollback_id": str(rollback.id), "profile_id": str(rollback.profile_id)},
            )
        )
        return rollback


__all__ = ["ConfigurationRollbackService"]
