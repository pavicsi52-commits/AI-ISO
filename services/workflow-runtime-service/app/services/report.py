"""Report generation. Per docs/042 "REPORTING" "Generate": Execution
Reports, Performance Reports, Failure Reports, Approval Reports,
Workflow History, Executive Dashboards. Matches the "GET-as-generate"
precedent ``services/playbook-service``'s own ``PlaybookReportService``
established: a report is computed and persisted the moment it's
requested, not queued for later.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.models.enums import WorkflowInstanceStatus, WorkflowReportType
from app.models.workflow_report import WorkflowReport
from app.repositories.workflow_approval import WorkflowApprovalRepository
from app.repositories.workflow_execution_step import WorkflowExecutionStepRepository
from app.repositories.workflow_instance import WorkflowInstanceRepository
from app.repositories.workflow_report import WorkflowReportRepository
from app.services.statistics import WorkflowStatisticsService


class WorkflowReportService:
    """Generates and lists workflow-runtime reports."""

    def __init__(
        self,
        reports: WorkflowReportRepository,
        instances: WorkflowInstanceRepository,
        steps: WorkflowExecutionStepRepository,
        approvals: WorkflowApprovalRepository,
        statistics: WorkflowStatisticsService,
    ) -> None:
        self._reports = reports
        self._instances = instances
        self._steps = steps
        self._approvals = approvals
        self._statistics = statistics

    async def list_for_org(
        self, organization_id: UUID, *, report_type: WorkflowReportType | None = None
    ) -> list[WorkflowReport]:
        """Every generated report for *organization_id* ("Generate")."""
        return await self._reports.list_for_org(organization_id, report_type=report_type)

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowReport]:
        """Every generated report scoped to *instance_id*."""
        return await self._reports.list_for_instance(instance_id)

    async def _execution_report(self, instance_id: UUID) -> dict[str, Any]:
        instance = await self._instances.require_by_id(instance_id)
        steps = await self._steps.list_for_instance(instance_id)
        return {
            "status": str(instance.status),
            "total_steps": len(steps),
            "started_at": instance.started_at.isoformat() if instance.started_at else None,
            "finished_at": instance.finished_at.isoformat() if instance.finished_at else None,
        }

    async def _performance_report(self, organization_id: UUID) -> dict[str, Any]:
        snapshot = await self._statistics.get_for_org(organization_id)
        return {
            "success_rate": snapshot.success_rate,
            "failure_rate": snapshot.failure_rate,
            "average_duration_seconds": snapshot.average_duration_seconds,
        }

    async def _failure_report(self, organization_id: UUID) -> dict[str, Any]:
        instances = await self._instances.list_for_org(
            organization_id, status=WorkflowInstanceStatus.FAILED
        )
        return {
            "total_failed": len(instances),
            "failed_instance_ids": [str(instance.id) for instance in instances],
        }

    async def _approval_report(self, instance_id: UUID) -> dict[str, Any]:
        entries = await self._approvals.list_for_instance(instance_id)
        return {
            "total_approvals": len(entries),
            "by_decision": dict(Counter(str(entry.decision) for entry in entries)),
        }

    async def _workflow_history_report(self, definition_id: UUID) -> dict[str, Any]:
        instances = await self._instances.list_for_definition(definition_id)
        return {
            "total_instances": len(instances),
            "by_status": dict(Counter(str(instance.status) for instance in instances)),
        }

    async def _executive_dashboard_report(self, organization_id: UUID) -> dict[str, Any]:
        snapshot = await self._statistics.get_for_org(organization_id)
        return {
            "total_workflows": snapshot.total_workflows,
            "total_executions": snapshot.total_executions,
            "success_rate": snapshot.success_rate,
            "approval_count": snapshot.approval_count,
            "rollback_count": snapshot.rollback_count,
        }

    async def generate(
        self,
        organization_id: UUID,
        *,
        report_type: WorkflowReportType,
        instance_id: UUID | None,
        definition_id: UUID | None,
        parameters: dict[str, Any],
        generated_by: UUID | None,
    ) -> WorkflowReport:
        """Generate and persist a report ("Generate").

        Raises:
            ValidationError: If *report_type* requires an *instance_id*/
                *definition_id* that wasn't given.
        """
        if report_type is WorkflowReportType.PERFORMANCE:
            result = await self._performance_report(organization_id)
        elif report_type is WorkflowReportType.FAILURE:
            result = await self._failure_report(organization_id)
        elif report_type is WorkflowReportType.EXECUTIVE_DASHBOARD:
            result = await self._executive_dashboard_report(organization_id)
        elif report_type is WorkflowReportType.WORKFLOW_HISTORY:
            if definition_id is None:
                raise ValidationError("A workflow_history report requires a definition_id.")
            result = await self._workflow_history_report(definition_id)
        elif instance_id is None:
            raise ValidationError(f"Report type {report_type!r} requires an instance_id.")
        elif report_type is WorkflowReportType.EXECUTION:
            result = await self._execution_report(instance_id)
        else:
            result = await self._approval_report(instance_id)

        return await self._reports.create(
            WorkflowReport(
                organization_id=organization_id,
                instance_id=instance_id,
                report_type=report_type,
                generated_by=generated_by,
                parameters=parameters,
                result=result,
                generated_at=datetime.now(UTC),
            )
        )


__all__ = ["WorkflowReportService"]
