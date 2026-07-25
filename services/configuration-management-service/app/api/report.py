"""``GET /configurations/reports``. Per docs/039 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, ReportSvc
from app.models.configuration_report import ConfigurationReport
from app.models.enums import ConfigReportType
from app.schemas.report import ConfigurationReportResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/configurations", tags=["Reports"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def report_to_response(report: ConfigurationReport) -> ConfigurationReportResponse:
    return ConfigurationReportResponse(
        id=report.id,
        organization_id=report.organization_id,
        profile_id=report.profile_id,
        report_type=report.report_type,
        generated_by=report.generated_by,
        parameters=report.parameters,
        result=report.result,
        generated_at=report.generated_at,
    )


@router.get("/reports", response_model=SuccessResponse[ConfigurationReportResponse])
async def generate_report(
    organization_id: UUID,
    report_type: ConfigReportType,
    reports: ReportSvc,
    caller: CurrentUserId,
    profile_id: UUID | None = None,
) -> SuccessResponse[ConfigurationReportResponse]:
    """Generate a configuration-management report ("Generate")."""
    report = await reports.generate(
        organization_id,
        report_type=report_type,
        profile_id=profile_id,
        parameters={},
        generated_by=caller,
    )
    return SuccessResponse(
        message="Configuration report generated.", data=report_to_response(report), meta=_meta()
    )


__all__ = ["report_to_response", "router"]
