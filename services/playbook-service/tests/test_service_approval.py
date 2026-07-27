"""Tests for :class:`app.services.approval.PlaybookApprovalService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ApprovalStatus, ApprovalType
from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_approval import PlaybookApprovalRepository
from app.services.approval import EventPublisher, PlaybookApprovalService
from tests.conftest import make_playbook


def _build_service(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> PlaybookApprovalService:
    return PlaybookApprovalService(
        PlaybookApprovalRepository(db_session),
        PlaybookRepository(db_session),
        publish_event=publish_event,
    )


class TestPlaybookApprovalService:
    async def test_request_creates_pending_approval(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        requester_id = uuid.uuid4()

        approval = await service.request(
            playbook.id,
            version_id=None,
            approval_type=ApprovalType.TECHNICAL,
            level=1,
            requested_by=requester_id,
        )
        assert approval.status == ApprovalStatus.PENDING
        assert approval.approval_type == ApprovalType.TECHNICAL
        assert approval.requested_by == requester_id

    async def test_request_for_missing_playbook_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.request(
                uuid.uuid4(),
                version_id=None,
                approval_type=ApprovalType.SECURITY,
                level=1,
                requested_by=None,
            )

    async def test_list_for_playbook(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        service = _build_service(db_session)
        await service.request(
            playbook.id,
            version_id=None,
            approval_type=ApprovalType.OPERATIONAL,
            level=1,
            requested_by=None,
        )
        approvals = await service.list_for_playbook(playbook.id)
        assert len(approvals) == 1

    async def test_list_pending_for_org(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        playbook = await make_playbook(db_session, organization_id=org_id)
        service = _build_service(db_session)
        await service.request(
            playbook.id,
            version_id=None,
            approval_type=ApprovalType.PUBLISHING,
            level=1,
            requested_by=None,
        )
        pending = await service.list_pending_for_org(org_id)
        assert len(pending) == 1

    async def test_decide_approved_publishes_approved_event(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        events: list[DomainEvent] = []

        async def _collect(event: DomainEvent) -> None:
            events.append(event)

        service = _build_service(db_session, publish_event=_collect)
        approval = await service.request(
            playbook.id,
            version_id=None,
            approval_type=ApprovalType.TECHNICAL,
            level=1,
            requested_by=None,
        )
        approver_id = uuid.uuid4()

        decided = await service.decide(
            approval.id, status=ApprovalStatus.APPROVED, approver_id=approver_id, comments="LGTM"
        )
        assert decided.status == ApprovalStatus.APPROVED
        assert decided.approver_id == approver_id
        assert decided.decided_at is not None
        assert [event.event_name for event in events] == ["PlaybookApproved"]

    async def test_decide_rejected_publishes_rejected_event(self, db_session: AsyncSession) -> None:
        playbook = await make_playbook(db_session)
        events: list[DomainEvent] = []

        async def _collect(event: DomainEvent) -> None:
            events.append(event)

        service = _build_service(db_session, publish_event=_collect)
        approval = await service.request(
            playbook.id,
            version_id=None,
            approval_type=ApprovalType.TECHNICAL,
            level=1,
            requested_by=None,
        )

        decided = await service.decide(
            approval.id, status=ApprovalStatus.REJECTED, approver_id=None, comments="Needs work."
        )
        assert decided.status == ApprovalStatus.REJECTED
        assert [event.event_name for event in events] == ["PlaybookRejected"]

    async def test_get_by_id_missing_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())
