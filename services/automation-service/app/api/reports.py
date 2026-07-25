"""``GET /automation/reports``. Per docs/040 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, ReportSvc
from app.models.automation_report import AutomationReport
from app.models.enums import AutomationReportType
from app.schemas.report import AutomationReportResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/automation/reports", tags=["Reports"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def report_to_response(report: AutomationReport) -> AutomationReportResponse:
    return AutomationReportResponse(
        id=report.id,
        organization_id=report.organization_id,
        job_id=report.job_id,
        report_type=report.report_type,
        generated_by=report.generated_by,
        parameters=report.parameters,
        result=report.result,
        generated_at=report.generated_at,
    )


@router.get("", response_model=SuccessResponse[AutomationReportResponse])
async def generate_report(
    organization_id: UUID,
    report_type: AutomationReportType,
    reports: ReportSvc,
    caller: CurrentUserId,
    job_id: UUID | None = None,
) -> SuccessResponse[AutomationReportResponse]:
    """Generate an automation report ("Generate")."""
    report = await reports.generate(
        organization_id,
        report_type=report_type,
        job_id=job_id,
        parameters={},
        generated_by=caller,
    )
    return SuccessResponse(
        message="Automation report generated.", data=report_to_response(report), meta=_meta()
    )


__all__ = ["report_to_response", "router"]
