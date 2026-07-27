"""``GET /playbooks/reports``. Per docs/041 REST list."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, ReportSvc
from app.models.enums import PlaybookReportType
from app.models.playbook_report import PlaybookReport
from app.schemas.report import PlaybookReportResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/playbooks/reports", tags=["Reports"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def report_to_response(report: PlaybookReport) -> PlaybookReportResponse:
    return PlaybookReportResponse(
        id=report.id,
        organization_id=report.organization_id,
        playbook_id=report.playbook_id,
        report_type=report.report_type,
        generated_by=report.generated_by,
        parameters=report.parameters,
        result=report.result,
        generated_at=report.generated_at,
    )


@router.get("", response_model=SuccessResponse[PlaybookReportResponse])
async def generate_report(
    organization_id: UUID,
    report_type: PlaybookReportType,
    reports: ReportSvc,
    caller: CurrentUserId,
    playbook_id: UUID | None = None,
) -> SuccessResponse[PlaybookReportResponse]:
    """Generate a playbook-repository report ("Generate")."""
    report = await reports.generate(
        organization_id,
        report_type=report_type,
        playbook_id=playbook_id,
        parameters={},
        generated_by=caller,
    )
    return SuccessResponse(
        message="Playbook report generated.", data=report_to_response(report), meta=_meta()
    )


__all__ = ["report_to_response", "router"]
