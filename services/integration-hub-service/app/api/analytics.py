"""Health dashboard, statistics, reporting, and audit (docs/058
"HEALTH MANAGEMENT", "ANALYTICS", "REPORTING", "AUDIT")."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response, status
from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, ConnectorSvc, CurrentUserId, HealthSvc, ReportSvc, StatisticsSvc
from app.models.enums import AuditAction, ReportFormat
from app.schemas.hub import (
    AuditEntryResponse,
    ReportGenerateRequest,
    ReportResponse,
    StatisticResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/integrations", tags=["Analytics"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "/health",
    response_model=SuccessResponse[list[dict[str, Any]]],
    summary="Org-wide connector health",
)
async def connector_health_dashboard(
    organization_id: UUID, connectors: ConnectorSvc, health: HealthSvc
) -> SuccessResponse[list[dict[str, Any]]]:
    """Every connector's own most recent health status, in one view."""
    rows = await connectors.list_for_org(organization_id, limit=1_000)
    dashboard = []
    for connector in rows:
        latest = await health.latest_for_connector(connector.id)
        dashboard.append(
            {
                "connector_id": str(connector.id),
                "name": connector.name,
                "status": str(latest.status) if latest else "unknown",
                "checked_at": latest.checked_at.isoformat() if latest else None,
            }
        )
    return SuccessResponse(message="Health dashboard computed.", data=dashboard, meta=_meta())


@router.get(
    "/statistics", response_model=SuccessResponse[dict[str, object]], summary="Traffic statistics"
)
async def get_statistics(
    organization_id: UUID, statistics: StatisticsSvc
) -> SuccessResponse[dict[str, object]]:
    """The live dashboard snapshot: latest window."""
    dashboard = await statistics.dashboard(organization_id)
    return SuccessResponse(message="Statistics computed.", data=dashboard, meta=_meta())


@router.get(
    "/statistics/trend",
    response_model=SuccessResponse[list[StatisticResponse]],
    summary="Statistics trend over recent windows",
)
async def get_statistics_trend(
    organization_id: UUID,
    statistics: StatisticsSvc,
    since_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> SuccessResponse[list[StatisticResponse]]:
    """Recent statistics windows, oldest first."""
    rows = await statistics.trend(organization_id, since_days=since_days)
    return SuccessResponse(
        message="Statistics trend listed.",
        data=[StatisticResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.get(
    "/reports", response_model=SuccessResponse[list[ReportResponse]], summary="List reports"
)
async def list_reports(
    organization_id: UUID,
    reports: ReportSvc,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[ReportResponse]]:
    """Generated reports, newest first."""
    rows = await reports.list_for_org(organization_id, limit=limit, offset=offset)
    return SuccessResponse(
        message="Reports listed.",
        data=[ReportResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.post(
    "/reports",
    response_model=SuccessResponse[ReportResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Generate a report",
)
async def generate_report(
    organization_id: UUID,
    body: ReportGenerateRequest,
    reports: ReportSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ReportResponse]:
    """Build and store a new report."""
    created = await reports.generate(
        organization_id,
        kind=body.kind,
        report_format=body.report_format,
        title=body.title,
        generated_by=str(caller),
    )
    await audit.record(
        organization_id,
        action=AuditAction.ADMINISTRATIVE,
        entity_type="report",
        entity_id=created.id,
        actor_id=str(caller),
        summary=f"Generated {created.kind!s} report.",
        succeeded=str(created.status) != "failed",
    )
    return SuccessResponse(
        message="Report generated.", data=ReportResponse.model_validate(created), meta=_meta()
    )


@router.get(
    "/reports/{report_id}", response_model=SuccessResponse[ReportResponse], summary="Get a report"
)
async def get_report(
    organization_id: UUID, report_id: UUID, reports: ReportSvc
) -> SuccessResponse[ReportResponse]:
    """One report."""
    found = await reports.require_in_org(organization_id, report_id)
    return SuccessResponse(
        message="Report found.", data=ReportResponse.model_validate(found), meta=_meta()
    )


@router.get("/reports/{report_id}/download", summary="Download a report as CSV or Markdown")
async def download_report(
    organization_id: UUID,
    report_id: UUID,
    reports: ReportSvc,
    report_format: Annotated[ReportFormat, Query()] = ReportFormat.CSV,
) -> Response:
    """Render a completed report to a downloadable file.

    Raises:
        NotFoundError: If the report does not exist, or has no content
            to render (still running, or failed).
    """
    found = await reports.require_in_org(organization_id, report_id)
    if not found.content:
        raise NotFoundError(f"Report {report_id} has no content to download.")
    if report_format == ReportFormat.MARKDOWN:
        body = reports.to_markdown(found.content, title=found.title)
        media_type, extension = "text/markdown", "md"
    else:
        body = reports.to_csv(found.content)
        media_type, extension = "text/csv", "csv"
    filename = f"{found.kind!s}-{report_id}.{extension}"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/audit", response_model=SuccessResponse[list[AuditEntryResponse]], summary="Audit trail"
)
async def list_audit(
    organization_id: UUID,
    audit: AuditSvc,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[AuditEntryResponse]]:
    """The append-only integration-hub-service audit trail, newest first."""
    rows = await audit.list_entries(organization_id, limit=limit, offset=offset)
    return SuccessResponse(
        message="Audit entries listed.",
        data=[AuditEntryResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


__all__ = ["router"]
