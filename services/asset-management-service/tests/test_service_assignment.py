"""Tests for :class:`app.services.assignment.AssetAssignmentService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from shared_core.events.base import DomainEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AssignmentStatus, AssignmentType
from app.repositories.asset_assignment import AssetAssignmentRepository
from app.services.assignment import AssetAssignmentService, EventPublisher
from tests.conftest import make_managed_asset


def _build(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> AssetAssignmentService:
    return AssetAssignmentService(
        AssetAssignmentRepository(db_session), publish_event=publish_event
    )


async def test_assign_creates_active_assignment(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    assignee_id = uuid.uuid4()

    assignment = await service.assign(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        assignee_id=assignee_id,
        assignment_type=AssignmentType.STANDARD,
        assigned_by=uuid.uuid4(),
        expires_at=None,
        notes="initial rollout",
    )

    assert assignment.assignee_id == assignee_id
    assert assignment.status == AssignmentStatus.ACTIVE


async def test_assign_publishes_event(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session, publish_event=_publish)

    await service.assign(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        assignee_id=uuid.uuid4(),
        assignment_type=AssignmentType.STANDARD,
        assigned_by=None,
        expires_at=None,
        notes=None,
    )

    assert any(event.event_name == "AssetAssigned" for event in published)


async def test_reassign_returns_prior_active_assignment(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)

    first = await service.assign(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        assignee_id=uuid.uuid4(),
        assignment_type=AssignmentType.STANDARD,
        assigned_by=None,
        expires_at=None,
        notes=None,
    )
    second = await service.assign(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        assignee_id=uuid.uuid4(),
        assignment_type=AssignmentType.STANDARD,
        assigned_by=None,
        expires_at=None,
        notes=None,
    )

    active = await AssetAssignmentRepository(db_session).get_active_for_managed_asset(
        managed_asset.id
    )
    assert active is not None
    assert active.id == second.id
    assert first.status == AssignmentStatus.RETURNED
    assert first.returned_at is not None


async def test_assign_temporary_with_expiry(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    expires_at = datetime.now(UTC) + timedelta(days=7)

    assignment = await service.assign(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        assignee_id=uuid.uuid4(),
        assignment_type=AssignmentType.TEMPORARY,
        assigned_by=None,
        expires_at=expires_at,
        notes=None,
    )

    assert assignment.assignment_type == AssignmentType.TEMPORARY
    assert assignment.expires_at == expires_at


async def test_list_for_managed_asset_returns_history(db_session: AsyncSession) -> None:
    managed_asset = await make_managed_asset(db_session)
    service = _build(db_session)
    await service.assign(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        assignee_id=uuid.uuid4(),
        assignment_type=AssignmentType.STANDARD,
        assigned_by=None,
        expires_at=None,
        notes=None,
    )
    await service.assign(
        managed_asset.id,
        organization_id=managed_asset.organization_id,
        assignee_id=uuid.uuid4(),
        assignment_type=AssignmentType.STANDARD,
        assigned_by=None,
        expires_at=None,
        notes=None,
    )

    history = await service.list_for_managed_asset(managed_asset.id)
    assert len(history) == 2
