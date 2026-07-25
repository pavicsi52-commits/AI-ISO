"""Configuration version history.

Per docs/039 "VERSIONING" "Support": Semantic Versioning, Configuration
History, Version Comparison, Rollback, Branching, Change Tracking,
Approval Workflow. Each snapshot's own :attr:`~app.models
.configuration_version.ConfigurationVersion.version_number` is bumped
via a real semantic-versioning patch increment ("Semantic Versioning")
computed from the branch's own most recent snapshot -- not a
caller-supplied free-text field, since two concurrent callers supplying
their own version numbers could collide or go backwards.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.models.configuration_version import ConfigurationVersion
from app.repositories.configuration_version import ConfigurationVersionRepository


def _bump_patch(version_number: str) -> str:
    """Increment the patch component of a ``MAJOR.MINOR.PATCH`` string."""
    major, minor, patch = version_number.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


class ConfigurationVersionService:
    """Creates and lists immutable configuration-profile snapshots."""

    def __init__(self, versions: ConfigurationVersionRepository) -> None:
        self._versions = versions

    async def get_by_id(self, version_id: UUID) -> ConfigurationVersion:
        """Return the version identified by *version_id*.

        Raises:
            NotFoundError: If no such version exists.
        """
        return await self._versions.require_by_id(version_id)

    async def list_for_profile(
        self, profile_id: UUID, *, branch: str | None = None
    ) -> list[ConfigurationVersion]:
        """Every version recorded for *profile_id*, newest first ("Configuration History")."""
        return await self._versions.list_for_profile(profile_id, branch=branch)

    async def get_latest_for_profile(
        self, profile_id: UUID, *, branch: str = "main"
    ) -> ConfigurationVersion | None:
        """Return *profile_id*'s most recently created version on *branch*, or ``None``."""
        return await self._versions.get_latest_for_profile(profile_id, branch=branch)

    async def create_snapshot(
        self,
        profile_id: UUID,
        *,
        organization_id: UUID,
        branch: str = "main",
        content: dict[str, Any],
        change_summary: str | None,
        changed_by: UUID | None,
    ) -> ConfigurationVersion:
        """Record a new immutable snapshot on *branch* ("Change Tracking").

        The first snapshot on a branch starts at ``1.0.0``; every
        subsequent one bumps the prior snapshot's patch component
        ("Semantic Versioning"). *organization_id* is the owning
        profile's own tenant id -- :class:`ConfigurationVersion` inherits
        a NOT NULL ``organization_id`` column like every AI-IOS entity,
        so it must always be supplied explicitly here rather than left
        to a database default.
        """
        latest = await self.get_latest_for_profile(profile_id, branch=branch)
        version_number = _bump_patch(latest.version_number) if latest is not None else "1.0.0"
        return await self._versions.create(
            ConfigurationVersion(
                organization_id=organization_id,
                profile_id=profile_id,
                version_number=version_number,
                branch=branch,
                content=content,
                change_summary=change_summary,
                changed_by=changed_by,
            )
        )

    async def record_approval(self, version_id: UUID, *, approved_by: UUID) -> ConfigurationVersion:
        """Mark *version_id* as approved ("Approval Workflow").

        Raises:
            NotFoundError: If no such version exists.
        """
        version = await self.get_by_id(version_id)
        version.approved_by = approved_by
        version.approved_at = datetime.now(UTC)
        return await self._versions.update(version)


__all__ = ["ConfigurationVersionService"]
