"""Tests for :class:`app.services.restore.ConfigurationRestoreService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.validation import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import BackupType, RestoreStatus, RestoreType
from app.repositories.configuration_backup import ConfigurationBackupRepository
from app.repositories.configuration_profile import ConfigurationProfileRepository
from app.repositories.configuration_restore_job import ConfigurationRestoreJobRepository
from app.services.backup import ConfigurationBackupService
from app.services.restore import ConfigurationRestoreService, EventPublisher
from tests.conftest import build_version_service, make_profile


def build_backup_service(db_session: AsyncSession) -> ConfigurationBackupService:
    return ConfigurationBackupService(
        ConfigurationBackupRepository(db_session), ConfigurationProfileRepository(db_session)
    )


def build_restore_service(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> ConfigurationRestoreService:
    return ConfigurationRestoreService(
        ConfigurationRestoreJobRepository(db_session),
        ConfigurationBackupRepository(db_session),
        ConfigurationProfileRepository(db_session),
        build_version_service(db_session),
        publish_event=publish_event,
    )


async def test_restore_applies_backup_content_and_publishes_event(
    db_session: AsyncSession,
) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    profile = await make_profile(db_session, variables={"port": "80"})
    backups = build_backup_service(db_session)
    backup = await backups.create_backup(
        profile.id, backup_type=BackupType.SNAPSHOT, encrypted=False, retention_until=None
    )

    profile.variables = {"port": "9090"}

    restores = build_restore_service(db_session, publish_event=_publish)
    job = await restores.restore(
        profile.id,
        backup_id=backup.id,
        restore_type=RestoreType.PROFILE,
        preview_only=False,
        requested_by=uuid.uuid4(),
    )

    assert job.status == RestoreStatus.COMPLETED
    assert job.organization_id == profile.organization_id
    assert profile.variables == {"port": "80"}
    assert any(event.event_name == "RestoreCompleted" for event in published)


async def test_restore_preview_only_does_not_mutate_profile(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    profile = await make_profile(db_session, variables={"port": "80"})
    backups = build_backup_service(db_session)
    backup = await backups.create_backup(
        profile.id, backup_type=BackupType.SNAPSHOT, encrypted=False, retention_until=None
    )
    profile.variables = {"port": "9090"}

    restores = build_restore_service(db_session, publish_event=_publish)
    job = await restores.restore(
        profile.id,
        backup_id=backup.id,
        restore_type=RestoreType.PREVIEW,
        preview_only=True,
        requested_by=None,
    )

    assert job.preview_only is True
    assert job.status == RestoreStatus.COMPLETED
    assert profile.variables == {"port": "9090"}
    assert published == []


async def test_restore_rejects_tampered_backup(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    backups = build_backup_service(db_session)
    backup = await backups.create_backup(
        profile.id, backup_type=BackupType.SNAPSHOT, encrypted=False, retention_until=None
    )
    backup.checksum = "tampered-checksum"

    restores = build_restore_service(db_session)
    with pytest.raises(ValidationError):
        await restores.restore(
            profile.id,
            backup_id=backup.id,
            restore_type=RestoreType.PROFILE,
            preview_only=False,
            requested_by=None,
        )


async def test_list_for_profile(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    backups = build_backup_service(db_session)
    backup = await backups.create_backup(
        profile.id, backup_type=BackupType.SNAPSHOT, encrypted=False, retention_until=None
    )
    restores = build_restore_service(db_session)
    await restores.restore(
        profile.id,
        backup_id=backup.id,
        restore_type=RestoreType.PROFILE,
        preview_only=True,
        requested_by=None,
    )

    jobs = await restores.list_for_profile(profile.id)
    assert len(jobs) == 1
