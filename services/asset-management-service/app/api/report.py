"""``GET /assets/reports``. Per docs/038 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, ReportSvc
from app.models.asset_report import AssetReport
from app.models.enums import ReportType
from app.schemas.report import AssetReportResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/assets", tags=["Reports"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def report_to_response(report: AssetReport) -> AssetReportResponse:
    return AssetReportResponse(
        id=report.id,
        organization_id=report.organization_id,
        managed_asset_id=report.managed_asset_id,
        report_type=report.report_type,
        generated_by=report.generated_by,
        parameters=report.parameters,
        result=report.result,
        generated_at=report.generated_at,
    )


@router.get("/reports", response_model=SuccessResponse[AssetReportResponse])
async def generate_report(
    organization_id: UUID,
    report_type: ReportType,
    reports: ReportSvc,
    caller: CurrentUserId,
    managed_asset_id: UUID | None = None,
) -> SuccessResponse[AssetReportResponse]:
    """Generate an asset-management report ("Generate")."""
    report = await reports.generate(
        organization_id,
        report_type=report_type,
        managed_asset_id=managed_asset_id,
        parameters={},
        generated_by=caller,
    )
    return SuccessResponse(
        message="Report generated.", data=report_to_response(report), meta=_meta()
    )


__all__ = ["report_to_response", "router"]
