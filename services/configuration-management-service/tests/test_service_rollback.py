"""Tests for :class:`app.services.rollback.ConfigurationRollbackService`."""

from __future__ import annotations

import uuid

from shared_core.events.base import DomainEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RollbackStatus, RollbackType
from app.repositories.configuration_profile import ConfigurationProfileRepository
from app.repositories.configuration_rollback import ConfigurationRollbackRepository
from app.services.rollback import ConfigurationRollbackService, EventPublisher
from tests.conftest import build_version_service, make_profile


def build_service(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> ConfigurationRollbackService:
    return ConfigurationRollbackService(
        ConfigurationRollbackRepository(db_session),
        build_version_service(db_session),
        ConfigurationProfileRepository(db_session),
        publish_event=publish_event,
    )


async def test_initiate_publishes_rollback_started(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    profile = await make_profile(db_session, variables={"a": "1"})
    versions = build_version_service(db_session)
    version = await versions.create_snapshot(
        profile.id,
        organization_id=profile.organization_id,
        content={"variables": {"a": "1"}, "target_assets": []},
        change_summary=None,
        changed_by=None,
    )

    service = build_service(db_session, publish_event=_publish)
    rollback = await service.initiate(
        profile.id,
        to_version_id=version.id,
        rollback_type=RollbackType.VERSION,
        requested_by=uuid.uuid4(),
        reason="Bad deploy.",
    )

    assert rollback.status == RollbackStatus.PENDING
    assert rollback.organization_id == profile.organization_id
    assert rollback.to_version_id == version.id
    assert any(event.event_name == "RollbackStarted" for event in published)


async def test_approve_marks_approved(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    versions = build_version_service(db_session)
    version = await versions.create_snapshot(
        profile.id,
        organization_id=profile.organization_id,
        content={"variables": {}, "target_assets": []},
        change_summary=None,
        changed_by=None,
    )
    service = build_service(db_session)
    rollback = await service.initiate(
        profile.id,
        to_version_id=version.id,
        rollback_type=RollbackType.FULL,
        requested_by=None,
        reason=None,
    )

    approver_id = uuid.uuid4()
    approved = await service.approve(rollback.id, approved_by=approver_id)
    assert approved.status == RollbackStatus.APPROVED
    assert approved.approved_by == approver_id


async def test_complete_applies_target_version_and_publishes_event(
    db_session: AsyncSession,
) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    profile = await make_profile(db_session, variables={"a": "1"})
    versions = build_version_service(db_session)
    target_version = await versions.create_snapshot(
        profile.id,
        organization_id=profile.organization_id,
        content={"variables": {"a": "0"}, "target_assets": ["asset-x"]},
        change_summary=None,
        changed_by=None,
    )

    service = build_service(db_session, publish_event=_publish)
    rollback = await service.initiate(
        profile.id,
        to_version_id=target_version.id,
        rollback_type=RollbackType.VERSION,
        requested_by=None,
        reason=None,
    )

    completed = await service.complete(rollback.id)

    assert completed.status == RollbackStatus.COMPLETED
    assert completed.completed_at is not None
    assert profile.variables == {"a": "0"}
    assert profile.target_assets == ["asset-x"]
    assert any(event.event_name == "RollbackCompleted" for event in published)


async def test_list_for_profile(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    versions = build_version_service(db_session)
    version = await versions.create_snapshot(
        profile.id,
        organization_id=profile.organization_id,
        content={"variables": {}, "target_assets": []},
        change_summary=None,
        changed_by=None,
    )
    service = build_service(db_session)
    await service.initiate(
        profile.id,
        to_version_id=version.id,
        rollback_type=RollbackType.INCREMENTAL,
        requested_by=None,
        reason=None,
    )

    records = await service.list_for_profile(profile.id)
    assert len(records) == 1
