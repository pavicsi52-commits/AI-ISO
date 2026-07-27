"""``GET /workflow/reports``. Per docs/042 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, ReportSvc
from app.models.enums import WorkflowReportType
from app.models.workflow_report import WorkflowReport
from app.schemas.report import WorkflowReportResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/workflow/reports", tags=["Reports"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def report_to_response(report: WorkflowReport) -> WorkflowReportResponse:
    return WorkflowReportResponse(
        id=report.id,
        organization_id=report.organization_id,
        instance_id=report.instance_id,
        report_type=report.report_type,
        generated_by=report.generated_by,
        parameters=report.parameters,
        result=report.result,
        generated_at=report.generated_at,
    )


@router.get("", response_model=SuccessResponse[WorkflowReportResponse])
async def generate_report(
    organization_id: UUID,
    report_type: WorkflowReportType,
    reports: ReportSvc,
    caller: CurrentUserId,
    instance_id: UUID | None = None,
    definition_id: UUID | None = None,
) -> SuccessResponse[WorkflowReportResponse]:
    """Generate a workflow-runtime report ("Generate")."""
    report = await reports.generate(
        organization_id,
        report_type=report_type,
        instance_id=instance_id,
        definition_id=definition_id,
        parameters={},
        generated_by=caller,
    )
    return SuccessResponse(
        message="Workflow report generated.", data=report_to_response(report), meta=_meta()
    )


__all__ = ["report_to_response", "router"]
