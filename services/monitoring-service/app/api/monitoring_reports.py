"""``GET /monitoring/reports``. Per docs/044 REST list. Matches the
"GET-as-generate" precedent ``services/validation-service``'s own
``GET /validation/reports`` already established: a report is computed
and persisted the moment it's requested.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, ReportSvc
from app.models.enums import MonitoringReportType
from app.models.monitoring_report import MonitoringReport
from app.schemas.report import MonitoringReportResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/monitoring/reports", tags=["Monitoring Reports"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def report_to_response(report: MonitoringReport) -> MonitoringReportResponse:
    return MonitoringReportResponse(
        id=report.id,
        organization_id=report.organization_id,
        target_id=report.target_id,
        report_type=report.report_type,
        generated_by=report.generated_by,
        parameters=report.parameters,
        result=report.result,
        generated_at=report.generated_at,
    )


@router.get("", response_model=SuccessResponse[MonitoringReportResponse])
async def generate_report(
    organization_id: UUID,
    report_type: MonitoringReportType,
    reports: ReportSvc,
    caller: CurrentUserId,
    target_id: UUID | None = None,
) -> SuccessResponse[MonitoringReportResponse]:
    """Generate a monitoring report ("Generate")."""
    report = await reports.generate(
        organization_id,
        report_type=report_type,
        target_id=target_id,
        parameters={},
        generated_by=caller,
    )
    return SuccessResponse(
        message="Monitoring report generated.", data=report_to_response(report), meta=_meta()
    )


__all__ = ["report_to_response", "router"]
