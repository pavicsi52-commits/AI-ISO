"""Tests for :class:`app.services.execution_log.AutomationExecutionLogService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_execution import AutomationExecution
from app.models.automation_execution_log import AutomationExecutionLog
from app.models.enums import ExecutionMode, ExecutionStatus, LogLevel
from app.repositories.automation_execution_log import AutomationExecutionLogRepository
from app.services.execution_log import AutomationExecutionLogService
from tests.conftest import make_job


def _build_service(db_session: AsyncSession) -> AutomationExecutionLogService:
    return AutomationExecutionLogService(AutomationExecutionLogRepository(db_session))


class TestAutomationExecutionLogService:
    async def test_list_for_execution_returns_oldest_first(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        execution = AutomationExecution(
            organization_id=job.organization_id,
            job_id=job.id,
            status=ExecutionStatus.RUNNING,
            execution_mode=ExecutionMode.MANUAL,
        )
        db_session.add(execution)
        await db_session.flush()

        first = AutomationExecutionLog(
            organization_id=job.organization_id,
            execution_id=execution.id,
            level=LogLevel.INFO,
            message="starting",
            logged_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        second = AutomationExecutionLog(
            organization_id=job.organization_id,
            execution_id=execution.id,
            level=LogLevel.INFO,
            message="finished",
            logged_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
        db_session.add_all([second, first])
        await db_session.flush()

        service = _build_service(db_session)
        logs = await service.list_for_execution(execution.id)
        assert [entry.message for entry in logs] == ["starting", "finished"]

    async def test_list_for_execution_empty(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        assert await service.list_for_execution(uuid.uuid4()) == []
