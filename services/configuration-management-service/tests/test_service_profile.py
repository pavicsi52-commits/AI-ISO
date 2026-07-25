"""Tests for :class:`app.services.profile.ConfigurationProfileService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ConfigurationType, EnvironmentType, ProfileStatus
from tests.conftest import build_profile_service, build_version_service, make_profile


async def test_create_defines_profile_and_first_version(db_session: AsyncSession) -> None:
    service = build_profile_service(db_session)
    org_id = uuid.uuid4()

    profile = await service.create(
        organization_id=org_id,
        project_id=None,
        profile_name="web-tier-baseline",
        description="Baseline for the web tier.",
        environment=EnvironmentType.PRODUCTION,
        owner_id=None,
        configuration_type=ConfigurationType.APPLICATION,
        target_assets=["asset-1"],
        variables={"port": "8080"},
        tags=["web"],
        metadata={"team": "platform"},
        created_by=uuid.uuid4(),
    )

    assert profile.profile_name == "web-tier-baseline"
    assert profile.status == ProfileStatus.DRAFT
    assert profile.profile_version == "1.0.0"

    versions = build_version_service(db_session)
    snapshots = await versions.list_for_profile(profile.id)
    assert len(snapshots) == 1
    assert snapshots[0].version_number == "1.0.0"
    assert snapshots[0].content["variables"] == {"port": "8080"}


async def test_create_publishes_event(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    service = build_profile_service(db_session, publish_event=_publish)
    await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        profile_name="db-tier",
        description=None,
        environment=EnvironmentType.STAGING,
        owner_id=None,
        configuration_type=ConfigurationType.DATABASE,
        target_assets=[],
        variables={},
        tags=[],
        metadata={},
        created_by=None,
    )

    assert any(event.event_name == "ConfigurationCreated" for event in published)


async def test_get_by_id_raises_not_found(db_session: AsyncSession) -> None:
    service = build_profile_service(db_session)
    with pytest.raises(NotFoundError):
        await service.get_by_id(uuid.uuid4())


async def test_list_for_org(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    await make_profile(db_session, organization_id=org_id)
    await make_profile(db_session, organization_id=org_id)
    await make_profile(db_session, organization_id=uuid.uuid4())

    service = build_profile_service(db_session)
    records = await service.list_for_org(org_id)
    assert len(records) == 2


async def test_search(db_session: AsyncSession) -> None:
    org_id = uuid.uuid4()
    await make_profile(db_session, organization_id=org_id, profile_name="Payments Profile")
    await make_profile(db_session, organization_id=org_id, profile_name="Orders Profile")

    service = build_profile_service(db_session)
    result = await service.search(
        query="Payments", filters=None, sort_fields=None, page=1, page_size=10
    )
    assert result.metadata.total == 1
    assert result.items[0].profile_name == "Payments Profile"


async def test_update_records_new_version_and_publishes_event(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    service = build_profile_service(db_session, publish_event=_publish)
    profile = await service.create(
        organization_id=uuid.uuid4(),
        project_id=None,
        profile_name="versioned-profile",
        description=None,
        environment=EnvironmentType.DEVELOPMENT,
        owner_id=None,
        configuration_type=ConfigurationType.APPLICATION,
        target_assets=[],
        variables={"a": "1"},
        tags=[],
        metadata={},
        created_by=None,
    )
    published.clear()

    updated = await service.update(
        profile.id,
        actor_id=uuid.uuid4(),
        profile_name=profile.profile_name,
        description="updated",
        status=ProfileStatus.ACTIVE,
        environment=profile.environment,
        owner_id=None,
        configuration_type=profile.configuration_type,
        target_assets=["asset-2"],
        variables={"a": "2"},
        tags=["prod"],
        metadata={},
        change_summary="Bumped a.",
    )

    assert updated.status == ProfileStatus.ACTIVE
    assert updated.variables == {"a": "2"}
    assert any(event.event_name == "ConfigurationUpdated" for event in published)

    versions = build_version_service(db_session)
    snapshots = await versions.list_for_profile(profile.id)
    assert len(snapshots) == 2
    assert snapshots[0].version_number == "1.0.1"


async def test_patch_only_changes_given_fields(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session, profile_name="original")
    service = build_profile_service(db_session)

    patched = await service.patch(profile.id, actor_id=uuid.uuid4(), description="new description")

    assert patched.description == "new description"
    assert patched.profile_name == "original"


async def test_patch_variables_records_new_version(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session, variables={"x": "1"})
    service = build_profile_service(db_session)

    await service.patch(profile.id, actor_id=None, variables={"x": "2"})

    versions = build_version_service(db_session)
    snapshots = await versions.list_for_profile(profile.id)
    assert len(snapshots) == 1


async def test_patch_metadata_field_maps_to_metadata_underscore(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_profile_service(db_session)

    patched = await service.patch(profile.id, actor_id=None, metadata={"k": "v"})

    assert patched.metadata_ == {"k": "v"}


async def test_delete_soft_deletes(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_profile_service(db_session)

    await service.delete(profile.id, actor_id=uuid.uuid4())

    with pytest.raises(NotFoundError):
        await service.get_by_id(profile.id)
