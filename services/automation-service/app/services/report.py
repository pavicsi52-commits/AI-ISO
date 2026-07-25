"""Report generation. Per docs/040 "REPORTING" "Generate": Execution
Reports, Failure Reports, Success Reports, Performance Reports,
Compliance Reports, Executive Dashboards, Automation Trends. Matches
the "GET-as-generate" precedent
``services/configuration-management-service``'s own
``ConfigurationReportService`` established: a report is computed and
persisted the moment it's requested, not queued for later.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.models.automation_report import AutomationReport
from app.models.enums import AutomationReportType, ExecutionStatus
from app.repositories.automation_report import AutomationReportRepository
from app.services.execution import AutomationExecutionService
from app.services.job import AutomationJobService
from app.services.statistics import AutomationStatisticsService


class AutomationReportService:
    """Generates and lists automation reports."""

    def __init__(
        self,
        reports: AutomationReportRepository,
        jobs: AutomationJobService,
        executions: AutomationExecutionService,
        statistics: AutomationStatisticsService,
    ) -> None:
        self._reports = reports
        self._jobs = jobs
        self._executions = executions
        self._statistics = statistics

    async def list_for_org(
        self, organization_id: UUID, *, report_type: AutomationReportType | None = None
    ) -> list[AutomationReport]:
        """Every generated report for *organization_id* ("Generate")."""
        return await self._reports.list_for_org(organization_id, report_type=report_type)

    async def list_for_job(self, job_id: UUID) -> list[AutomationReport]:
        """Every generated report scoped to *job_id*."""
        return await self._reports.list_for_job(job_id)

    async def _execution_report(self, job_id: UUID) -> dict[str, Any]:
        executions = await self._executions.list_for_job(job_id)
        return {
            "total_executions": len(executions),
            "by_status": {
                str(status): sum(1 for e in executions if e.status == status)
                for status in {e.status for e in executions}
            },
        }

    async def _failure_report(self, job_id: UUID) -> dict[str, Any]:
        executions = await self._executions.list_for_job(job_id)
        failures = [e for e in executions if e.status == ExecutionStatus.FAILED]
        return {
            "total_failures": len(failures),
            "failure_messages": [e.error_message for e in failures if e.error_message][:20],
        }

    async def _success_report(self, job_id: UUID) -> dict[str, Any]:
        executions = await self._executions.list_for_job(job_id)
        successes = [e for e in executions if e.status == ExecutionStatus.COMPLETED]
        return {"total_successes": len(successes), "total_executions": len(executions)}

    async def _performance_report(self, job_id: UUID) -> dict[str, Any]:
        executions = await self._executions.list_for_job(job_id)
        durations = [
            (e.completed_at - e.started_at).total_seconds()
            for e in executions
            if e.started_at is not None and e.completed_at is not None
        ]
        return {
            "total_executions_measured": len(durations),
            "average_runtime_seconds": sum(durations) / len(durations) if durations else 0.0,
            "max_runtime_seconds": max(durations) if durations else 0.0,
            "min_runtime_seconds": min(durations) if durations else 0.0,
        }

    async def _compliance_report(self, job_id: UUID) -> dict[str, Any]:
        job = await self._jobs.get_by_id(job_id)
        return {"job_status": str(job.status), "automation_type": str(job.automation_type)}

    async def _executive_dashboard_report(self, organization_id: UUID) -> dict[str, Any]:
        snapshot = await self._statistics.get_for_org(organization_id)
        return {
            "total_jobs": snapshot.total_jobs,
            "total_executions": snapshot.total_executions,
            "success_rate": snapshot.success_rate,
            "failure_rate": snapshot.failure_rate,
            "top_failed_jobs": snapshot.top_failed_jobs,
            "most_executed_jobs": snapshot.most_executed_jobs,
        }

    async def _automation_trends_report(self, organization_id: UUID) -> dict[str, Any]:
        snapshot = await self._statistics.get_for_org(organization_id)
        return {
            "execution_heatmap": snapshot.execution_heatmap,
            "connector_usage": snapshot.connector_usage,
            "average_runtime_seconds": snapshot.average_runtime_seconds,
        }

    async def _build_result(
        self, organization_id: UUID, *, report_type: AutomationReportType, job_id: UUID | None
    ) -> dict[str, Any]:
        if report_type is AutomationReportType.EXECUTIVE_DASHBOARD:
            return await self._executive_dashboard_report(organization_id)
        if report_type is AutomationReportType.AUTOMATION_TRENDS:
            return await self._automation_trends_report(organization_id)
        if job_id is None:
            raise ValidationError(f"Report type {report_type!r} requires a job_id.")

        builders: dict[AutomationReportType, Callable[[UUID], Awaitable[dict[str, Any]]]] = {
            AutomationReportType.EXECUTION: self._execution_report,
            AutomationReportType.FAILURE: self._failure_report,
            AutomationReportType.SUCCESS: self._success_report,
            AutomationReportType.PERFORMANCE: self._performance_report,
            AutomationReportType.COMPLIANCE: self._compliance_report,
        }
        return await builders[report_type](job_id)

    async def generate(
        self,
        organization_id: UUID,
        *,
        report_type: AutomationReportType,
        job_id: UUID | None,
        parameters: dict[str, Any],
        generated_by: UUID | None,
    ) -> AutomationReport:
        """Generate and persist a report ("Generate")."""
        result = await self._build_result(organization_id, report_type=report_type, job_id=job_id)
        return await self._reports.create(
            AutomationReport(
                organization_id=organization_id,
                job_id=job_id,
                report_type=report_type,
                generated_by=generated_by,
                parameters=parameters,
                result=result,
                generated_at=datetime.now(UTC),
            )
        )


__all__ = ["AutomationReportService"]
