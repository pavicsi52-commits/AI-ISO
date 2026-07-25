"""Restore a configuration profile from a backup.

Per docs/039 "RESTORE" "Support": Restore Profile, Restore Version,
Selective Restore, Bulk Restore, Preview Restore, Validation, Audit.
Every restore re-derives the backup's own SHA-256
("Validation") before applying it, matching
:func:`app.services.backup.compute_checksum`; ``preview_only`` runs the
same integrity check without mutating the profile ("Preview Restore").
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from shared_core.events.base import DomainEvent
from shared_core.exceptions.validation import ValidationError

from app.events.configuration_events import RestoreCompletedEvent
from app.models.configuration_restore_job import ConfigurationRestoreJob
from app.models.enums import RestoreStatus, RestoreType
from app.repositories.configuration_backup import ConfigurationBackupRepository
from app.repositories.configuration_profile import ConfigurationProfileRepository
from app.repositories.configuration_restore_job import ConfigurationRestoreJobRepository
from app.services.backup import compute_checksum
from app.services.version import ConfigurationVersionService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class ConfigurationRestoreService:
    """Restores (or previews restoring) a configuration profile from a backup."""

    def __init__(
        self,
        restore_jobs: ConfigurationRestoreJobRepository,
        backups: ConfigurationBackupRepository,
        profiles: ConfigurationProfileRepository,
        versions: ConfigurationVersionService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._restore_jobs = restore_jobs
        self._backups = backups
        self._profiles = profiles
        self._versions = versions
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, job_id: UUID) -> ConfigurationRestoreJob:
        """Return the restore job identified by *job_id*.

        Raises:
            NotFoundError: If no such restore job exists.
        """
        return await self._restore_jobs.require_by_id(job_id)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationRestoreJob]:
        """Every restore job recorded for *profile_id*."""
        return await self._restore_jobs.list_for_profile(profile_id)

    async def restore(
        self,
        profile_id: UUID,
        *,
        backup_id: UUID,
        restore_type: RestoreType,
        preview_only: bool,
        requested_by: UUID | None,
    ) -> ConfigurationRestoreJob:
        """Restore *profile_id* from *backup_id* ("Restore Profile"),
        publishing ``RestoreCompleted`` when actually applied.

        Raises:
            ValidationError: If the backup's content fails checksum
                verification ("Validation").
        """
        backup = await self._backups.require_by_id(backup_id)
        if backup.checksum != compute_checksum(backup.content):
            raise ValidationError(f"Backup {backup_id} failed integrity verification.")
        profile = await self._profiles.require_by_id(profile_id)

        job = await self._restore_jobs.create(
            ConfigurationRestoreJob(
                organization_id=profile.organization_id,
                backup_id=backup_id,
                profile_id=profile_id,
                restore_type=restore_type,
                status=RestoreStatus.IN_PROGRESS,
                preview_only=preview_only,
                requested_by=requested_by,
            )
        )

        if not preview_only:
            profile.variables = backup.content.get("variables", {})
            profile.target_assets = backup.content.get("target_assets", [])
            profile.tags = backup.content.get("tags", [])
            profile.metadata_ = backup.content.get("metadata", {})
            await self._profiles.update(profile)
            await self._versions.create_snapshot(
                profile_id,
                organization_id=profile.organization_id,
                content={
                    "variables": profile.variables,
                    "target_assets": profile.target_assets,
                },
                change_summary=f"Restored from backup {backup_id}.",
                changed_by=requested_by,
            )

        job.status = RestoreStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
        job = await self._restore_jobs.update(job)

        if not preview_only:
            await self._publish(
                RestoreCompletedEvent(
                    source_service="configuration-management-service",
                    payload={"restore_job_id": str(job.id), "profile_id": str(profile_id)},
                )
            )
        return job


__all__ = ["ConfigurationRestoreService"]
