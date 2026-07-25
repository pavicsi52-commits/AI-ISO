"""Tests for :class:`app.services.approval.ConfigurationApprovalService`."""

from __future__ import annotations

import uuid

from shared_core.events.base import DomainEvent
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ApprovalStatus
from app.repositories.configuration_approval import ConfigurationApprovalRepository
from app.services.approval import ConfigurationApprovalService, EventPublisher
from tests.conftest import make_profile


def build_service(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> ConfigurationApprovalService:
    return ConfigurationApprovalService(
        ConfigurationApprovalRepository(db_session), publish_event=publish_event
    )


async def test_request_creates_pending_approval(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    requester_id = uuid.uuid4()

    approval = await service.request(
        organization_id=profile.organization_id,
        profile_id=profile.id,
        version_id=None,
        rollback_id=None,
        level=1,
        requested_by=requester_id,
    )

    assert approval.status == ApprovalStatus.PENDING
    assert approval.requested_by == requester_id


async def test_decide_approved_publishes_configuration_approved(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    profile = await make_profile(db_session)
    service = build_service(db_session, publish_event=_publish)
    approval = await service.request(
        organization_id=profile.organization_id,
        profile_id=profile.id,
        version_id=None,
        rollback_id=None,
        level=1,
        requested_by=None,
    )

    approver_id = uuid.uuid4()
    decided = await service.decide(
        approval.id, status=ApprovalStatus.APPROVED, approver_id=approver_id, comments="LGTM"
    )

    assert decided.status == ApprovalStatus.APPROVED
    assert decided.decided_at is not None
    assert any(event.event_name == "ConfigurationApproved" for event in published)


async def test_decide_rejected_publishes_configuration_rejected(db_session: AsyncSession) -> None:
    published: list[DomainEvent] = []

    async def _publish(event: DomainEvent) -> None:
        published.append(event)

    profile = await make_profile(db_session)
    service = build_service(db_session, publish_event=_publish)
    approval = await service.request(
        organization_id=profile.organization_id,
        profile_id=profile.id,
        version_id=None,
        rollback_id=None,
        level=1,
        requested_by=None,
    )

    await service.decide(
        approval.id, status=ApprovalStatus.REJECTED, approver_id=None, comments="Needs work."
    )

    assert any(event.event_name == "ConfigurationRejected" for event in published)


async def test_resubmit_reopens_for_decision(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    approval = await service.request(
        organization_id=profile.organization_id,
        profile_id=profile.id,
        version_id=None,
        rollback_id=None,
        level=1,
        requested_by=None,
    )
    await service.decide(
        approval.id, status=ApprovalStatus.REJECTED, approver_id=None, comments=None
    )

    resubmitted = await service.resubmit(approval.id)
    assert resubmitted.status == ApprovalStatus.RESUBMITTED
    assert resubmitted.decided_at is None


async def test_list_for_profile_and_pending_for_org(db_session: AsyncSession) -> None:
    profile = await make_profile(db_session)
    service = build_service(db_session)
    await service.request(
        organization_id=profile.organization_id,
        profile_id=profile.id,
        version_id=None,
        rollback_id=None,
        level=1,
        requested_by=None,
    )

    for_profile = await service.list_for_profile(profile.id)
    assert len(for_profile) == 1

    pending = await service.list_pending_for_org(profile.organization_id)
    assert len(pending) == 1
