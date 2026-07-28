"""``/alert-statistics`` and ``/alert-reports``."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import CurrentUserId, ReportSvc, StatisticsSvc
from app.models.alert_report import AlertReport
from app.models.enums import AlertReportType
from app.schemas.report import AlertReportGenerateRequest, AlertReportResponse
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.statistics import AlertStatisticsResponse

statistics_router = APIRouter(prefix="/alert-statistics", tags=["Alert Analytics"])
reports_router = APIRouter(prefix="/alert-reports", tags=["Alert Reports"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def report_to_response(report: AlertReport) -> AlertReportResponse:
    """Map an :class:`AlertReport` row onto its own response schema."""
    return AlertReportResponse(
        id=report.id,
        organization_id=report.organization_id,
        alert_id=report.alert_id,
        report_type=report.report_type,
        generated_by=report.generated_by,
        parameters=report.parameters,
        result=report.result,
        generated_at=report.generated_at,
    )


@statistics_router.get("", response_model=SuccessResponse[AlertStatisticsResponse])
async def get_alert_statistics(
    organization_id: UUID,
    statistics: StatisticsSvc,
    _caller: CurrentUserId,
    recompute: bool = False,
) -> SuccessResponse[AlertStatisticsResponse]:
    """An organization's alerting analytics rollup.

    Cached by default; ``recompute=true`` forces a fresh computation.
    """
    snapshot = (
        await statistics.recompute(organization_id)
        if recompute
        else await statistics.get_for_org(organization_id)
    )
    data = AlertStatisticsResponse(
        total_alerts=snapshot.total_alerts,
        open_alert_count=snapshot.open_alert_count,
        noise_ratio=snapshot.noise_ratio,
        suppression_rate=snapshot.suppression_rate,
        average_resolution_seconds=snapshot.average_resolution_seconds,
        mtta_seconds=snapshot.mtta_seconds,
        mttr_seconds=snapshot.mttr_seconds,
        top_sources=snapshot.top_sources,
        top_rules=snapshot.top_rules,
        escalation_statistics=snapshot.escalation_statistics,
        trend_data=snapshot.trend_data,
        computed_at=snapshot.computed_at,
    )
    return SuccessResponse(message="Alert statistics retrieved.", data=data, meta=_meta())


@reports_router.get("", response_model=SuccessResponse[list[AlertReportResponse]])
async def list_alert_reports(
    organization_id: UUID,
    reports: ReportSvc,
    _caller: CurrentUserId,
    report_type: AlertReportType | None = None,
) -> SuccessResponse[list[AlertReportResponse]]:
    """List previously generated reports."""
    records = await reports.list_for_org(organization_id, report_type=report_type)
    data = [report_to_response(record) for record in records]
    return SuccessResponse(message="Alert reports retrieved.", data=data, meta=_meta())


@reports_router.post("", response_model=SuccessResponse[AlertReportResponse], status_code=201)
async def generate_alert_report(
    body: AlertReportGenerateRequest, reports: ReportSvc, caller: CurrentUserId
) -> SuccessResponse[AlertReportResponse]:
    """Generate and persist a report.

    Added beyond docs/045's own literal ``GET /alert-reports`` entry --
    that list has no way to *produce* a report, only read ones that
    already exist.

    Raises:
        ValidationError: If an ``ALERT`` report is requested with no ``alert_id``.
        NotFoundError: If the named alert does not exist.
    """
    report = await reports.generate(
        body.organization_id,
        report_type=body.report_type,
        alert_id=body.alert_id,
        parameters=body.parameters,
        generated_by=caller,
    )
    return SuccessResponse(
        message="Alert report generated.", data=report_to_response(report), meta=_meta()
    )


__all__ = ["report_to_response", "reports_router", "statistics_router"]
