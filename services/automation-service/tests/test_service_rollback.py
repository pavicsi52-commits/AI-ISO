"""Tests for :class:`app.services.rollback.AutomationRollbackService`."""

from __future__ import annotations

import uuid

import pytest
from shared_core.events.base import DomainEvent
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.automation_events import RollbackCompletedEvent, RollbackStartedEvent
from app.models.automation_execution import AutomationExecution
from app.models.enums import ExecutionMode, ExecutionStatus, RollbackStatus, RollbackType
from app.repositories.automation_execution import AutomationExecutionRepository
from app.repositories.automation_rollback import AutomationRollbackRepository
from app.services.rollback import AutomationRollbackService, EventPublisher
from tests.conftest import make_job


async def _make_execution(db_session: AsyncSession) -> AutomationExecution:
    job = await make_job(db_session)
    execution = AutomationExecution(
        organization_id=job.organization_id,
        job_id=job.id,
        status=ExecutionStatus.FAILED,
        execution_mode=ExecutionMode.MANUAL,
    )
    db_session.add(execution)
    await db_session.flush()
    return execution


def _build_service(
    db_session: AsyncSession, *, publish_event: EventPublisher | None = None
) -> AutomationRollbackService:
    return AutomationRollbackService(
        AutomationRollbackRepository(db_session),
        AutomationExecutionRepository(db_session),
        publish_event=publish_event,
    )


class TestAutomationRollbackService:
    async def test_initiate_publishes_started_event(self, db_session: AsyncSession) -> None:
        execution = await _make_execution(db_session)
        published: list[DomainEvent] = []

        async def _publish(event: DomainEvent) -> None:
            published.append(event)

        service = _build_service(db_session, publish_event=_publish)
        rollback = await service.initiate(
            execution.id,
            rollback_type=RollbackType.EXECUTION,
            initiated_by=uuid.uuid4(),
            reason="bad deploy",
        )
        assert rollback.status == RollbackStatus.PENDING
        assert rollback.organization_id == execution.organization_id
        assert len(published) == 1
        assert isinstance(published[0], RollbackStartedEvent)

    async def test_initiate_missing_execution_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.initiate(
                uuid.uuid4(),
                rollback_type=RollbackType.MANUAL,
                initiated_by=None,
                reason=None,
            )

    async def test_complete_success_publishes_completed_event(
        self, db_session: AsyncSession
    ) -> None:
        execution = await _make_execution(db_session)
        published: list[DomainEvent] = []

        async def _publish(event: DomainEvent) -> None:
            published.append(event)

        service = _build_service(db_session, publish_event=_publish)
        rollback = await service.initiate(
            execution.id,
            rollback_type=RollbackType.AUTOMATIC,
            initiated_by=None,
            reason=None,
        )
        completed = await service.complete(rollback.id, succeeded=True)
        assert completed.status == RollbackStatus.COMPLETED
        assert completed.completed_at is not None
        assert any(isinstance(e, RollbackCompletedEvent) for e in published)

    async def test_complete_failure_does_not_publish_completed_event(
        self, db_session: AsyncSession
    ) -> None:
        execution = await _make_execution(db_session)
        published: list[DomainEvent] = []

        async def _publish(event: DomainEvent) -> None:
            published.append(event)

        service = _build_service(db_session, publish_event=_publish)
        rollback = await service.initiate(
            execution.id,
            rollback_type=RollbackType.STEP,
            initiated_by=None,
            reason=None,
        )
        published.clear()
        completed = await service.complete(rollback.id, succeeded=False)
        assert completed.status == RollbackStatus.FAILED
        assert not any(isinstance(e, RollbackCompletedEvent) for e in published)

    async def test_list_for_execution(self, db_session: AsyncSession) -> None:
        execution = await _make_execution(db_session)
        service = _build_service(db_session)
        await service.initiate(
            execution.id, rollback_type=RollbackType.PLAYBOOK, initiated_by=None, reason=None
        )
        rollbacks = await service.list_for_execution(execution.id)
        assert len(rollbacks) == 1
