"""Tests for :class:`app.services.report.AutomationReportService`."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from shared_core.connectors.manager import ConnectorManager
from shared_core.exceptions.validation import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_execution import AutomationExecution
from app.models.automation_job import AutomationJob
from app.models.enums import AutomationReportType, ExecutionMode, ExecutionStatus
from app.repositories.automation_audit import AutomationAuditRepository
from app.repositories.automation_execution import AutomationExecutionRepository
from app.repositories.automation_execution_log import AutomationExecutionLogRepository
from app.repositories.automation_execution_step import AutomationExecutionStepRepository
from app.repositories.automation_job import AutomationJobRepository
from app.repositories.automation_output import AutomationOutputRepository
from app.repositories.automation_report import AutomationReportRepository
from app.repositories.automation_result import AutomationResultRepository
from app.repositories.automation_retry_history import AutomationRetryHistoryRepository
from app.repositories.automation_statistics import AutomationStatisticsRepository
from app.repositories.automation_target import AutomationTargetRepository
from app.secrets.credential_resolver import SecretCredentialResolver
from app.services.audit import AutomationAuditService
from app.services.execution import AutomationExecutionService
from app.services.job import AutomationJobService
from app.services.report import AutomationReportService
from app.services.statistics import AutomationStatisticsService
from tests.conftest import make_job


def _build_service(db_session: AsyncSession) -> AutomationReportService:
    jobs = AutomationJobService(
        AutomationJobRepository(db_session),
        AutomationAuditService(AutomationAuditRepository(db_session)),
    )
    executions = AutomationExecutionService(
        AutomationExecutionRepository(db_session),
        AutomationExecutionStepRepository(db_session),
        AutomationExecutionLogRepository(db_session),
        AutomationOutputRepository(db_session),
        AutomationResultRepository(db_session),
        AutomationRetryHistoryRepository(db_session),
        AutomationJobRepository(db_session),
        AutomationTargetRepository(db_session),
        ConnectorManager(),
        SecretCredentialResolver(httpx.AsyncClient(), base_url="http://unused"),
    )
    statistics = AutomationStatisticsService(
        AutomationStatisticsRepository(db_session),
        AutomationJobRepository(db_session),
        AutomationExecutionRepository(db_session),
        AutomationExecutionStepRepository(db_session),
        AutomationTargetRepository(db_session),
    )
    return AutomationReportService(
        AutomationReportRepository(db_session), jobs, executions, statistics
    )


async def _make_execution(
    db_session: AsyncSession,
    job: AutomationJob,
    *,
    status: ExecutionStatus,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    error_message: str | None = None,
) -> AutomationExecution:
    execution = AutomationExecution(
        organization_id=job.organization_id,
        job_id=job.id,
        status=status,
        execution_mode=ExecutionMode.MANUAL,
        started_at=started_at,
        completed_at=completed_at,
        error_message=error_message,
    )
    db_session.add(execution)
    await db_session.flush()
    return execution


class TestAutomationReportService:
    async def test_generate_execution_report(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        await _make_execution(db_session, job, status=ExecutionStatus.COMPLETED)
        service = _build_service(db_session)
        report = await service.generate(
            job.organization_id,
            report_type=AutomationReportType.EXECUTION,
            job_id=job.id,
            parameters={},
            generated_by=uuid.uuid4(),
        )
        assert report.report_type == AutomationReportType.EXECUTION
        assert report.result["total_executions"] == 1

    async def test_generate_failure_report(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        await _make_execution(db_session, job, status=ExecutionStatus.FAILED, error_message="boom")
        service = _build_service(db_session)
        report = await service.generate(
            job.organization_id,
            report_type=AutomationReportType.FAILURE,
            job_id=job.id,
            parameters={},
            generated_by=None,
        )
        assert report.result["total_failures"] == 1
        assert "boom" in report.result["failure_messages"]

    async def test_generate_success_report(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        await _make_execution(db_session, job, status=ExecutionStatus.COMPLETED)
        service = _build_service(db_session)
        report = await service.generate(
            job.organization_id,
            report_type=AutomationReportType.SUCCESS,
            job_id=job.id,
            parameters={},
            generated_by=None,
        )
        assert report.result["total_successes"] == 1

    async def test_generate_performance_report(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        started = datetime(2026, 1, 1, tzinfo=UTC)
        await _make_execution(
            db_session,
            job,
            status=ExecutionStatus.COMPLETED,
            started_at=started,
            completed_at=started + timedelta(seconds=15),
        )
        service = _build_service(db_session)
        report = await service.generate(
            job.organization_id,
            report_type=AutomationReportType.PERFORMANCE,
            job_id=job.id,
            parameters={},
            generated_by=None,
        )
        assert report.result["average_runtime_seconds"] == 15.0

    async def test_generate_compliance_report(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        report = await service.generate(
            job.organization_id,
            report_type=AutomationReportType.COMPLIANCE,
            job_id=job.id,
            parameters={},
            generated_by=None,
        )
        assert report.result["job_status"] == str(job.status)

    async def test_generate_executive_dashboard_report_ignores_job_id(
        self, db_session: AsyncSession
    ) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        report = await service.generate(
            job.organization_id,
            report_type=AutomationReportType.EXECUTIVE_DASHBOARD,
            job_id=None,
            parameters={},
            generated_by=None,
        )
        assert "total_jobs" in report.result

    async def test_generate_automation_trends_report(self, db_session: AsyncSession) -> None:
        org_id = uuid.uuid4()
        service = _build_service(db_session)
        report = await service.generate(
            org_id,
            report_type=AutomationReportType.AUTOMATION_TRENDS,
            job_id=None,
            parameters={},
            generated_by=None,
        )
        assert "execution_heatmap" in report.result

    async def test_generate_without_job_id_raises_validation_error(
        self, db_session: AsyncSession
    ) -> None:
        service = _build_service(db_session)
        with pytest.raises(ValidationError, match="requires a job_id"):
            await service.generate(
                uuid.uuid4(),
                report_type=AutomationReportType.EXECUTION,
                job_id=None,
                parameters={},
                generated_by=None,
            )

    async def test_list_for_org_and_list_for_job(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        await service.generate(
            job.organization_id,
            report_type=AutomationReportType.COMPLIANCE,
            job_id=job.id,
            parameters={},
            generated_by=None,
        )
        by_org = await service.list_for_org(job.organization_id)
        by_job = await service.list_for_job(job.id)
        assert len(by_org) == 1
        assert len(by_job) == 1

    async def test_list_for_org_filters_by_report_type(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        await service.generate(
            job.organization_id,
            report_type=AutomationReportType.COMPLIANCE,
            job_id=job.id,
            parameters={},
            generated_by=None,
        )
        filtered = await service.list_for_org(
            job.organization_id, report_type=AutomationReportType.EXECUTION
        )
        assert filtered == []
