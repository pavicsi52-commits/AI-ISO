"""Tests for :class:`app.services.audit.AutomationAuditService`."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_execution import AutomationExecution
from app.models.enums import AuditOutcome, ExecutionMode, ExecutionStatus
from app.repositories.automation_audit import AutomationAuditRepository
from app.services.audit import AutomationAuditService
from tests.conftest import make_job


def _build_service(db_session: AsyncSession) -> AutomationAuditService:
    return AutomationAuditService(AutomationAuditRepository(db_session))


class TestAutomationAuditService:
    async def test_record_and_list_for_job(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        entry = await service.record(
            job_id=job.id,
            execution_id=None,
            organization_id=job.organization_id,
            actor_id=uuid.uuid4(),
            action="create",
            after={"name": job.name},
        )
        assert entry.action == "create"
        assert entry.outcome == AuditOutcome.SUCCESS

        entries = await service.list_for_job(job.id)
        assert len(entries) == 1
        assert entries[0].id == entry.id

    async def test_record_with_failure_outcome(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        entry = await service.record(
            job_id=job.id,
            execution_id=None,
            organization_id=job.organization_id,
            actor_id=None,
            action="delete",
            outcome=AuditOutcome.FAILURE,
            reason="denied",
        )
        assert entry.outcome == AuditOutcome.FAILURE
        assert entry.reason == "denied"

    async def test_list_for_execution(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        execution = AutomationExecution(
            organization_id=job.organization_id,
            job_id=job.id,
            status=ExecutionStatus.PENDING,
            execution_mode=ExecutionMode.MANUAL,
        )
        db_session.add(execution)
        await db_session.flush()
        service = _build_service(db_session)
        await service.record(
            job_id=None,
            execution_id=execution.id,
            organization_id=job.organization_id,
            actor_id=None,
            action="cancel",
        )
        entries = await service.list_for_execution(execution.id)
        assert len(entries) == 1
        assert entries[0].action == "cancel"

    async def test_list_for_job_empty(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        assert await service.list_for_job(uuid.uuid4()) == []
