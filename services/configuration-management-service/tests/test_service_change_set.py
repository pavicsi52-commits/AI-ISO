"""Tests for :class:`app.services.change_set.ConfigurationChangeSetService`."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ChangeSetStatus
from app.repositories.configuration_change_set import ConfigurationChangeSetRepository
from app.repositories.configuration_profile import ConfigurationProfileRepository
from app.services.change_set import ConfigurationChangeSetService
from tests.conftest import build_version_service, make_profile


def build_service(db_session: AsyncSession) -> ConfigurationChangeSetService:
    return ConfigurationChangeSetService(
        ConfigurationChangeSetRepository(db_session),
        ConfigurationProfileRepository(db_session),
        build_version_service(db_session),
    )


async def test_create_change_set(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    creator_id = uuid.uuid4()

    change_set = await service.create(
        profile.id,
        changes=[{"key": "port", "value": "8080"}],
        created_by=creator_id,
    )

    assert change_set.profile_id == profile.id
    assert change_set.organization_id == profile.organization_id
    assert change_set.status == ChangeSetStatus.DRAFT
    assert change_set.created_by == creator_id


async def test_apply_merges_changes_into_profile_variables(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session, variables={"port": "80", "host": "localhost"})
    service = build_service(db_session)
    change_set = await service.create(
        profile.id,
        changes=[{"key": "port", "value": "9090"}, {"key": "timeout", "value": "30"}],
        created_by=None,
    )

    applied = await service.apply(change_set.id, actor_id=uuid.uuid4())

    assert applied.status == ChangeSetStatus.APPLIED
    assert applied.applied_at is not None
    assert profile.variables == {"port": "9090", "host": "localhost", "timeout": "30"}

    versions = build_version_service(db_session)
    snapshots = await versions.list_for_profile(profile.id)
    assert len(snapshots) == 1


async def test_revert_marks_reverted(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    change_set = await service.create(profile.id, changes=[], created_by=None)
    await service.apply(change_set.id, actor_id=None)

    reverted = await service.revert(change_set.id)
    assert reverted.status == ChangeSetStatus.REVERTED


async def test_list_for_profile(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    await service.create(profile.id, changes=[], created_by=None)

    records = await service.list_for_profile(profile.id)
    assert len(records) == 1
