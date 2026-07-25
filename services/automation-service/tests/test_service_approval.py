"""Tests for :class:`app.services.approval.AutomationApprovalService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.automation_events import ApprovalGrantedEvent, ApprovalRequestedEvent
from app.models.automation_execution import AutomationExecution
from app.models.enums import ApprovalStatus, ApprovalType, ExecutionMode, ExecutionStatus
from app.repositories.automation_approval import AutomationApprovalRepository
from app.repositories.automation_execution import AutomationExecutionRepository
from app.services.approval import AutomationApprovalService, EventPublisher
from tests.conftest import make_job


async def _make_execution(db_session: AsyncSession) -> AutomationExecution:
    job = await make_job(db_session)
    execution = AutomationExecution(
        organization_id=job.organization_id,
        job_id=job.id,
        status=ExecutionStatus.PENDING,
        execution_mode=ExecutionMode.APPROVAL_REQUIRED,
    )
    db_session.add(execution)
    await db_session.flush()
    return execution


def _build_service(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> AutomationApprovalService:
    return AutomationApprovalService(
        AutomationApprovalRepository(db_session),
        AutomationExecutionRepository(db_session),
        publish_event=publish_event,
    )


class TestAutomationApprovalService:
    async def test_request_publishes_requested_event(self, db_session: AsyncSession) -> None:
        execution = await _make_execution(db_session)
        published: list[DomainEvent] = []

        async def _publish(event: DomainEvent) -> None:
            published.append(event)

        service = _build_service(db_session, publish_event=_publish)
        approval = await service.request(
            execution.id,
            approval_type=ApprovalType.SINGLE,
            level=1,
            requested_by=uuid.uuid4(),
            expires_at=None,
        )
        assert approval.status == ApprovalStatus.PENDING
        assert isinstance(published[0], ApprovalRequestedEvent)

    async def test_request_missing_execution_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.request(
                uuid.uuid4(),
                approval_type=ApprovalType.SINGLE,
                level=1,
                requested_by=None,
                expires_at=None,
            )

    async def test_decide_approved_publishes_granted_event(self, db_session: AsyncSession) -> None:
        execution = await _make_execution(db_session)
        published: list[DomainEvent] = []

        async def _publish(event: DomainEvent) -> None:
            published.append(event)

        service = _build_service(db_session, publish_event=_publish)
        approval = await service.request(
            execution.id,
            approval_type=ApprovalType.ROLE_BASED,
            level=1,
            requested_by=None,
            expires_at=None,
        )
        published.clear()
        decided = await service.decide(
            approval.id, status=ApprovalStatus.APPROVED, approver_id=uuid.uuid4(), comments="ok"
        )
        assert decided.status == ApprovalStatus.APPROVED
        assert decided.decided_at is not None
        assert isinstance(published[0], ApprovalGrantedEvent)

    async def test_decide_rejected_does_not_publish_granted_event(
        self, db_session: AsyncSession
    ) -> None:
        execution = await _make_execution(db_session)
        published: list[DomainEvent] = []

        async def _publish(event: DomainEvent) -> None:
            published.append(event)

        service = _build_service(db_session, publish_event=_publish)
        approval = await service.request(
            execution.id,
            approval_type=ApprovalType.CONDITIONAL,
            level=1,
            requested_by=None,
            expires_at=None,
        )
        published.clear()
        decided = await service.decide(
            approval.id, status=ApprovalStatus.REJECTED, approver_id=uuid.uuid4(), comments="no"
        )
        assert decided.status == ApprovalStatus.REJECTED
        assert published == []

    async def test_list_pending_for_org(self, db_session: AsyncSession) -> None:
        execution = await _make_execution(db_session)
        service = _build_service(db_session)
        await service.request(
            execution.id,
            approval_type=ApprovalType.EMERGENCY_OVERRIDE,
            level=1,
            requested_by=None,
            expires_at=None,
        )
        pending = await service.list_pending_for_org(execution.organization_id)
        assert len(pending) == 1

    async def test_expire_stale_marks_past_expiry_pending_approvals(
        self, db_session: AsyncSession
    ) -> None:
        execution = await _make_execution(db_session)
        service = _build_service(db_session)
        await service.request(
            execution.id,
            approval_type=ApprovalType.SINGLE,
            level=1,
            requested_by=None,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        expired = await service.expire_stale(execution.organization_id)
        assert len(expired) == 1
        assert expired[0].status == ApprovalStatus.EXPIRED

    async def test_expire_stale_ignores_not_yet_expired(self, db_session: AsyncSession) -> None:
        execution = await _make_execution(db_session)
        service = _build_service(db_session)
        await service.request(
            execution.id,
            approval_type=ApprovalType.SINGLE,
            level=1,
            requested_by=None,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        expired = await service.expire_stale(execution.organization_id)
        assert expired == []
