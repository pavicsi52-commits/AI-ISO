"""Tests for :class:`app.services.assignment.ConfigurationAssignmentService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ConfigurationAssignmentStatus
from app.repositories.configuration_assignment import ConfigurationAssignmentRepository
from app.repositories.configuration_profile import ConfigurationProfileRepository
from app.services.assignment import ConfigurationAssignmentService, EventPublisher
from tests.conftest import make_profile


def build_service(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> ConfigurationAssignmentService:
    return ConfigurationAssignmentService(
        ConfigurationAssignmentRepository(db_session),
        ConfigurationProfileRepository(db_session),
        publish_event=publish_event,
    )


async def test_assign_creates_assignment_and_stores_organization_id(
    db_session: AsyncSession,
) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    managed_asset_id = uuid.uuid4()

    assignment = await service.assign(
        profile.id, managed_asset_id=managed_asset_id, assigned_by=uuid.uuid4()
    )

    assert assignment.profile_id == profile.id
    assert assignment.managed_asset_id == managed_asset_id
    assert assignment.organization_id == profile.organization_id
    assert assignment.status == ConfigurationAssignmentStatus.PENDING


async def test_assign_publishes_event(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    profile = await make_profile(db_session)
    service = build_service(db_session, publish_event=_publish)

    await service.assign(profile.id, managed_asset_id=uuid.uuid4(), assigned_by=None)

    assert any(event.event_name == "ConfigurationAssigned" for event in published)


async def test_assign_rejects_duplicate_pair(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    managed_asset_id = uuid.uuid4()
    await service.assign(profile.id, managed_asset_id=managed_asset_id, assigned_by=None)

    with pytest.raises(ConflictError):
        await service.assign(profile.id, managed_asset_id=managed_asset_id, assigned_by=None)


async def test_list_for_profile_and_managed_asset(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    managed_asset_id = uuid.uuid4()
    await service.assign(profile.id, managed_asset_id=managed_asset_id, assigned_by=None)

    for_profile = await service.list_for_profile(profile.id)
    assert len(for_profile) == 1

    for_asset = await service.list_for_managed_asset(managed_asset_id)
    assert len(for_asset) == 1


async def test_set_status_and_unassign(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    assignment = await service.assign(profile.id, managed_asset_id=uuid.uuid4(), assigned_by=None)

    updated = await service.set_status(assignment.id, ConfigurationAssignmentStatus.ACTIVE)
    assert updated.status == ConfigurationAssignmentStatus.ACTIVE

    await service.unassign(assignment.id)
    assert await service.list_for_profile(profile.id) == []
