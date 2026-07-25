"""Grouped, reviewable field-level configuration changes.

Per docs/039 "VERSIONING" "Change Tracking". A change set records a
list of ``{"key": ..., "value": ...}`` variable edits; applying it
merges those edits into the profile's own
:attr:`~app.models.configuration_profile.ConfigurationProfile
.variables` and records a new version snapshot -- the diff *produces*
the next :class:`~app.models.configuration_version.ConfigurationVersion`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.models.configuration_change_set import ConfigurationChangeSet
from app.models.enums import ChangeSetStatus
from app.repositories.configuration_change_set import ConfigurationChangeSetRepository
from app.repositories.configuration_profile import ConfigurationProfileRepository
from app.services.version import ConfigurationVersionService


class ConfigurationChangeSetService:
    """Creates and applies grouped configuration change sets."""

    def __init__(
        self,
        change_sets: ConfigurationChangeSetRepository,
        profiles: ConfigurationProfileRepository,
        versions: ConfigurationVersionService,
    ) -> None:
        self._change_sets = change_sets
        self._profiles = profiles
        self._versions = versions

    async def get_by_id(self, change_set_id: UUID) -> ConfigurationChangeSet:
        """Return the change set identified by *change_set_id*.

        Raises:
            NotFoundError: If no such change set exists.
        """
        return await self._change_sets.require_by_id(change_set_id)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationChangeSet]:
        """Every change set recorded for *profile_id*, newest first."""
        return await self._change_sets.list_for_profile(profile_id)

    async def create(
        self, profile_id: UUID, *, changes: list[dict[str, Any]], created_by: UUID | None
    ) -> ConfigurationChangeSet:
        """Group a set of proposed field-level changes as a draft."""
        profile = await self._profiles.require_by_id(profile_id)
        return await self._change_sets.create(
            ConfigurationChangeSet(
                organization_id=profile.organization_id,
                profile_id=profile_id,
                status=ChangeSetStatus.DRAFT,
                changes=changes,
                created_by=created_by,
            ),
            actor_id=created_by,
        )

    async def apply(self, change_set_id: UUID, *, actor_id: UUID | None) -> ConfigurationChangeSet:
        """Merge a draft change set's edits into its profile's variables
        and record a new version snapshot.
        """
        change_set = await self.get_by_id(change_set_id)
        profile = await self._profiles.require_by_id(change_set.profile_id)

        variables = dict(profile.variables)
        for change in change_set.changes:
            variables[change["key"]] = change["value"]
        profile.variables = variables
        await self._profiles.update(profile)

        await self._versions.create_snapshot(
            change_set.profile_id,
            organization_id=profile.organization_id,
            content={"variables": variables, "target_assets": profile.target_assets},
            change_summary=f"Applied change set {change_set_id}.",
            changed_by=actor_id,
        )

        change_set.status = ChangeSetStatus.APPLIED
        change_set.applied_at = datetime.now(UTC)
        return await self._change_sets.update(change_set)

    async def revert(self, change_set_id: UUID) -> ConfigurationChangeSet:
        """Mark a previously applied change set as reverted (the actual
        field rollback happens via :class:`~app.services.rollback
        .ConfigurationRollbackService` against a prior version).
        """
        change_set = await self.get_by_id(change_set_id)
        change_set.status = ChangeSetStatus.REVERTED
        return await self._change_sets.update(change_set)


__all__ = ["ConfigurationChangeSetService"]
