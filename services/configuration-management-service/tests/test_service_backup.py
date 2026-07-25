"""Tests for :class:`app.services.backup.ConfigurationBackupService`."""

from __future__ import annotations

from shared_core.events.base import DomainEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import BackupStatus, BackupType
from app.repositories.configuration_backup import ConfigurationBackupRepository
from app.repositories.configuration_profile import ConfigurationProfileRepository
from app.services.backup import ConfigurationBackupService, EventPublisher, compute_checksum
from tests.conftest import make_profile


def build_service(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> ConfigurationBackupService:
    return ConfigurationBackupService(
        ConfigurationBackupRepository(db_session),
        ConfigurationProfileRepository(db_session),
        publish_event=publish_event,
    )


async def test_compute_checksum_is_stable_and_order_independent() -> None:
    first = compute_checksum({"a": 1, "b": 2})
    second = compute_checksum({"b": 2, "a": 1})
    assert first == second

    different = compute_checksum({"a": 1, "b": 3})
    assert different != first


async def test_create_backup_snapshots_profile_state(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session, variables={"port": "80"})
    service = build_service(db_session)

    backup = await service.create_backup(
        profile.id,
        backup_type=BackupType.SNAPSHOT,
        encrypted=False,
        retention_until=None,
    )

    assert backup.profile_id == profile.id
    assert backup.organization_id == profile.organization_id
    assert backup.status == BackupStatus.COMPLETED
    assert backup.content["variables"] == {"port": "80"}
    assert backup.checksum == compute_checksum(backup.content)


async def test_create_backup_publishes_event(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    profile = await make_profile(db_session)
    service = build_service(db_session, publish_event=_publish)

    await service.create_backup(
        profile.id, backup_type=BackupType.EXPORT, encrypted=True, retention_until=None
    )

    assert any(event.event_name == "BackupCreated" for event in published)


async def test_list_for_profile(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    await service.create_backup(
        profile.id,
        backup_type=BackupType.CONFIGURATION_BACKUP,
        encrypted=False,
        retention_until=None,
    )

    backups = await service.list_for_profile(profile.id)
    assert len(backups) == 1

    fetched = await service.get_by_id(backups[0].id)
    assert fetched.id == backups[0].id
