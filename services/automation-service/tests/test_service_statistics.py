"""Tests for :class:`app.services.statistics.AutomationStatisticsService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_execution import AutomationExecution
from app.models.automation_execution_step import AutomationExecutionStep
from app.models.automation_job import AutomationJob
from app.models.enums import ExecutionMode, ExecutionStatus, ExecutionStepStatus
from app.repositories.automation_execution import AutomationExecutionRepository
from app.repositories.automation_execution_step import AutomationExecutionStepRepository
from app.repositories.automation_job import AutomationJobRepository
from app.repositories.automation_statistics import AutomationStatisticsRepository
from app.repositories.automation_target import AutomationTargetRepository
from app.services.statistics import AutomationStatisticsService
from tests.conftest import make_job, make_target


def _build_service(db_session: AsyncSession) -> AutomationStatisticsService:
    return AutomationStatisticsService(
        AutomationStatisticsRepository(db_session),
        AutomationJobRepository(db_session),
        AutomationExecutionRepository(db_session),
        AutomationExecutionStepRepository(db_session),
        AutomationTargetRepository(db_session),
    )


async def _make_execution(
    db_session: AsyncSession,
    job: AutomationJob,
    *,
    status: ExecutionStatus,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> AutomationExecution:
    execution = AutomationExecution(
        organization_id=job.organization_id,
        job_id=job.id,
        status=status,
        execution_mode=ExecutionMode.MANUAL,
        started_at=started_at,
        completed_at=completed_at,
    )
    db_session.add(execution)
    await db_session.flush()
    return execution


class TestAutomationStatisticsService:
    async def test_get_for_org_recomputes_when_none_cached(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        service = _build_service(db_session)
        snapshot = await service.get_for_org(org_id)
        assert snapshot.total_jobs == 0
        assert snapshot.total_executions == 0
        assert snapshot.success_rate == 0.0

    async def test_get_for_org_returns_cached_on_second_call(
        self, db_session: AsyncSession
    ) -> None:
        org_id = uuid.uuid4()
        service = _build_service(db_session)
        first = await service.get_for_org(org_id)
        second = await service.get_for_org(org_id)
        assert first.id == second.id

    async def test_recompute_counts_success_and_failure_rates(
        self, db_session: AsyncSession
    ) -> None:
        job = await make_job(db_session)
        started = datetime(2026, 1, 1, tzinfo=UTC)
        await _make_execution(
            db_session,
            job,
            status=ExecutionStatus.COMPLETED,
            started_at=started,
            completed_at=started + timedelta(seconds=30),
        )
        await _make_execution(
            db_session,
            job,
            status=ExecutionStatus.FAILED,
            started_at=started,
            completed_at=started + timedelta(seconds=10),
        )

        service = _build_service(db_session)
        snapshot = await service.recompute(job.organization_id)

        assert snapshot.total_jobs == 1
        assert snapshot.total_executions == 2
        assert snapshot.success_rate == 0.5
        assert snapshot.failure_rate == 0.5
        assert snapshot.average_runtime_seconds == 20.0
        assert snapshot.resource_usage == {}

    async def test_recompute_updates_existing_snapshot_in_place(
        self, db_session: AsyncSession
    ) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        first = await service.recompute(job.organization_id)

        await _make_execution(db_session, job, status=ExecutionStatus.COMPLETED)
        second = await service.recompute(job.organization_id)

        assert first.id == second.id
        assert second.total_executions == 1

    async def test_recompute_connector_usage_counts_by_target(
        self, db_session: AsyncSession
    ) -> None:
        job = await make_job(db_session)
        target = await make_target(db_session, organization_id=job.organization_id)
        execution = await _make_execution(db_session, job, status=ExecutionStatus.COMPLETED)
        step = AutomationExecutionStep(
            organization_id=job.organization_id,
            execution_id=execution.id,
            step_index=0,
            name=target.name,
            status=ExecutionStepStatus.COMPLETED,
            target_id=target.id,
        )
        db_session.add(step)
        await db_session.flush()

        service = _build_service(db_session)
        snapshot = await service.recompute(job.organization_id)
        assert snapshot.connector_usage == {"ssh": 1}

    async def test_recompute_top_failed_and_most_executed_jobs(
        self, db_session: AsyncSession
    ) -> None:
        job = await make_job(db_session, name="flaky-job")
        await _make_execution(db_session, job, status=ExecutionStatus.FAILED)
        await _make_execution(db_session, job, status=ExecutionStatus.COMPLETED)

        service = _build_service(db_session)
        snapshot = await service.recompute(job.organization_id)
        assert snapshot.most_executed_jobs == {"flaky-job": 2}
        assert snapshot.top_failed_jobs == {"flaky-job": 1}

    async def test_recompute_with_no_executions_has_zero_average_runtime(
        self, db_session: AsyncSession
    ) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        snapshot = await service.recompute(job.organization_id)
        assert snapshot.average_runtime_seconds == 0.0
        assert snapshot.execution_heatmap == {}
