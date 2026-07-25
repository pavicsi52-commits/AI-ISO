"""Configuration backup/snapshot/export.

Per docs/039 "BACKUP" "Support": Configuration Backup, Snapshot,
Export, Scheduled Backup, Retention Policies, Integrity Verification,
Encryption. :attr:`~app.models.configuration_backup.ConfigurationBackup
.checksum` is a real SHA-256 of the backed-up content's canonical JSON
form ("Integrity Verification") -- :class:`~app.services.restore
.ConfigurationRestoreService` re-derives it before restoring to detect
tampering.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.configuration_events import BackupCreatedEvent
from app.models.configuration_backup import ConfigurationBackup
from app.models.enums import BackupStatus, BackupType
from app.repositories.configuration_backup import ConfigurationBackupRepository
from app.repositories.configuration_profile import ConfigurationProfileRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


def compute_checksum(content: dict[str, Any]) -> str:
    """A stable SHA-256 of *content*'s canonical (sorted-key) JSON form
    ("Integrity Verification").
    """
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _snapshot_content(
    profile_name: str,
    variables: dict[str, Any],
    target_assets: list[str],
    tags: list[str],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "profile_name": profile_name,
        "variables": variables,
        "target_assets": target_assets,
        "tags": tags,
        "metadata": metadata,
    }


class ConfigurationBackupService:
    """Creates and lists configuration profile backups/snapshots/exports."""

    def __init__(
        self,
        backups: ConfigurationBackupRepository,
        profiles: ConfigurationProfileRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._backups = backups
        self._profiles = profiles
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, backup_id: UUID) -> ConfigurationBackup:
        """Return the backup identified by *backup_id*.

        Raises:
            NotFoundError: If no such backup exists.
        """
        return await self._backups.require_by_id(backup_id)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationBackup]:
        """Every backup recorded for *profile_id*, newest first."""
        return await self._backups.list_for_profile(profile_id)

    async def create_backup(
        self,
        profile_id: UUID,
        *,
        backup_type: BackupType,
        encrypted: bool,
        retention_until: datetime | None,
    ) -> ConfigurationBackup:
        """Snapshot *profile_id*'s current full state ("Configuration
        Backup"/"Snapshot"/"Export"), publishing ``BackupCreated``.
        """
        profile = await self._profiles.require_by_id(profile_id)
        content = _snapshot_content(
            profile.profile_name,
            profile.variables,
            profile.target_assets,
            profile.tags,
            profile.metadata_,
        )
        backup = await self._backups.create(
            ConfigurationBackup(
                organization_id=profile.organization_id,
                profile_id=profile_id,
                backup_type=backup_type,
                status=BackupStatus.COMPLETED,
                content=content,
                checksum=compute_checksum(content),
                encrypted=encrypted,
                retention_until=retention_until,
            )
        )
        await self._publish(
            BackupCreatedEvent(
                source_service="configuration-management-service",
                payload={"backup_id": str(backup.id), "profile_id": str(profile_id)},
            )
        )
        return backup


__all__ = ["ConfigurationBackupService", "compute_checksum"]
