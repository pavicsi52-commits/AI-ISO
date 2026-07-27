"""``GET /validation/reports``. Per docs/043 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, ReportSvc
from app.models.enums import ValidationReportType
from app.models.validation_report import ValidationReport
from app.schemas.report import ValidationReportResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/validation/reports", tags=["Reports"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def report_to_response(report: ValidationReport) -> ValidationReportResponse:
    return ValidationReportResponse(
        id=report.id,
        organization_id=report.organization_id,
        execution_id=report.execution_id,
        report_type=report.report_type,
        generated_by=report.generated_by,
        parameters=report.parameters,
        result=report.result,
        generated_at=report.generated_at,
    )


@router.get("", response_model=SuccessResponse[ValidationReportResponse])
async def generate_report(
    organization_id: UUID,
    report_type: ValidationReportType,
    reports: ReportSvc,
    caller: CurrentUserId,
    execution_id: UUID | None = None,
    target_id: UUID | None = None,
) -> SuccessResponse[ValidationReportResponse]:
    """Generate a validation report ("Generate")."""
    report = await reports.generate(
        organization_id,
        report_type=report_type,
        execution_id=execution_id,
        target_id=target_id,
        parameters={},
        generated_by=caller,
    )
    return SuccessResponse(
        message="Validation report generated.", data=report_to_response(report), meta=_meta()
    )


__all__ = ["report_to_response", "router"]
