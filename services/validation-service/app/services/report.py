"""Report generation. Per docs/043 "REPORTING" "Generate": Validation
Reports, Compliance Reports, Security Reports, Executive Reports,
Operational Reports, Trend Reports, Asset Reports. Matches the
"GET-as-generate" precedent ``services/workflow-runtime-service``'s own
``WorkflowReportService`` established: a report is computed and
persisted the moment it's requested, not queued for later.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.models.enums import ValidationReportType, ValidationSeverity
from app.models.validation_report import ValidationReport
from app.repositories.validation_execution import ValidationExecutionRepository
from app.repositories.validation_failure import ValidationFailureRepository
from app.repositories.validation_history import ValidationHistoryRepository
from app.repositories.validation_report import ValidationReportRepository
from app.repositories.validation_result import ValidationResultRepository
from app.services.statistics import ValidationStatisticsService


class ValidationReportService:
    """Generates and lists validation reports."""

    def __init__(
        self,
        reports: ValidationReportRepository,
        executions: ValidationExecutionRepository,
        results: ValidationResultRepository,
        failures: ValidationFailureRepository,
        history: ValidationHistoryRepository,
        statistics: ValidationStatisticsService,
    ) -> None:
        self._reports = reports
        self._executions = executions
        self._results = results
        self._failures = failures
        self._history = history
        self._statistics = statistics

    async def list_for_org(
        self, organization_id: UUID, *, report_type: ValidationReportType | None = None
    ) -> list[ValidationReport]:
        """Every generated report for *organization_id* ("Generate")."""
        return await self._reports.list_for_org(organization_id, report_type=report_type)

    async def _validation_report(self, execution_id: UUID) -> dict[str, Any]:
        execution = await self._executions.require_by_id(execution_id)
        results = await self._results.list_for_execution(execution_id)
        return {
            "status": str(execution.status),
            "total_results": len(results),
            "by_status": dict(Counter(str(result.status) for result in results)),
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "finished_at": execution.finished_at.isoformat() if execution.finished_at else None,
        }

    async def _compliance_report(self, organization_id: UUID) -> dict[str, Any]:
        failures = await self._failures.list_unresolved_for_org(organization_id)
        compliance_failures = [f for f in failures if f.severity == ValidationSeverity.CRITICAL]
        return {
            "total_unresolved_failures": len(failures),
            "critical_failure_count": len(compliance_failures),
        }

    async def _security_report(self, organization_id: UUID) -> dict[str, Any]:
        failures = await self._failures.list_unresolved_for_org(organization_id)
        return {
            "total_unresolved_failures": len(failures),
            "by_severity": dict(Counter(str(f.severity) for f in failures)),
        }

    async def _executive_report(self, organization_id: UUID) -> dict[str, Any]:
        snapshot = await self._statistics.get_for_org(organization_id)
        return {
            "total_profiles": snapshot.total_profiles,
            "total_executions": snapshot.total_executions,
            "pass_rate": snapshot.pass_rate,
            "failure_rate": snapshot.failure_rate,
        }

    async def _operational_report(self, organization_id: UUID) -> dict[str, Any]:
        snapshot = await self._statistics.get_for_org(organization_id)
        return {
            "total_executions": snapshot.total_executions,
            "average_duration_seconds": snapshot.average_duration_seconds,
            "top_failures": snapshot.top_failures,
        }

    async def _trend_report(self, organization_id: UUID) -> dict[str, Any]:
        snapshot = await self._statistics.get_for_org(organization_id)
        return {"trend_data": snapshot.trend_data, "compliance_trends": snapshot.compliance_trends}

    async def _asset_report(self, target_id: UUID) -> dict[str, Any]:
        records = await self._history.list_for_target(target_id)
        return {
            "total_snapshots": len(records),
            "scores": [record.score for record in records],
        }

    async def generate(
        self,
        organization_id: UUID,
        *,
        report_type: ValidationReportType,
        execution_id: UUID | None,
        target_id: UUID | None,
        parameters: dict[str, Any],
        generated_by: UUID | None,
    ) -> ValidationReport:
        """Generate and persist a report ("Generate").

        Raises:
            ValidationError: If *report_type* requires an *execution_id*/
                *target_id* that wasn't given.
        """
        if report_type is ValidationReportType.COMPLIANCE:
            result = await self._compliance_report(organization_id)
        elif report_type is ValidationReportType.SECURITY:
            result = await self._security_report(organization_id)
        elif report_type is ValidationReportType.EXECUTIVE:
            result = await self._executive_report(organization_id)
        elif report_type is ValidationReportType.OPERATIONAL:
            result = await self._operational_report(organization_id)
        elif report_type is ValidationReportType.TREND:
            result = await self._trend_report(organization_id)
        elif report_type is ValidationReportType.ASSET:
            if target_id is None:
                raise ValidationError("An asset report requires a target_id.")
            result = await self._asset_report(target_id)
        else:
            if execution_id is None:
                raise ValidationError(f"Report type {report_type!r} requires an execution_id.")
            result = await self._validation_report(execution_id)

        return await self._reports.create(
            ValidationReport(
                organization_id=organization_id,
                execution_id=execution_id,
                report_type=report_type,
                generated_by=generated_by,
                parameters=parameters,
                result=result,
                generated_at=datetime.now(UTC),
            )
        )


__all__ = ["ValidationReportService"]
