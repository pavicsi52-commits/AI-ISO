"""Statistics, reports, and audit (docs/055 "ANALYTICS", "REPORTING", "AUDIT")."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, status
from fastapi.responses import PlainTextResponse
from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, ReportSvc, StatisticsSvc
from app.models.enums import AuditAction, ReportFormat, ReportStatus, report_format_of, report_status_of
from app.schemas.notification import (
    AuditEntryResponse,
    ReportGenerateRequest,
    ReportResponse,
    StatisticResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/notifications", tags=["Analytics"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get(
    "/statistics",
    response_model=SuccessResponse[dict[str, Any]],
    summary="The live statistics dashboard snapshot",
)
async def get_statistics(
    organization_id: UUID, statistics: StatisticsSvc
) -> SuccessResponse[dict[str, Any]]:
    """The live snapshot a dashboard reads on load."""
    dashboard = await statistics.dashboard(organization_id)
    return SuccessResponse(message="Statistics computed.", data=dashboard, meta=_meta())


@router.get(
    "/statistics/trend",
    response_model=SuccessResponse[list[StatisticResponse]],
    summary="Recent rolled-up windows",
)
async def get_statistics_trend(
    organization_id: UUID,
    statistics: StatisticsSvc,
    since_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> SuccessResponse[list[StatisticResponse]]:
    """Recent statistics windows, oldest first, for a trend chart."""
    rows = await statistics.trend(organization_id, since_days=since_days)
    return SuccessResponse(
        message="Trend computed.",
        data=[StatisticResponse.model_validate(row) for row in rows],
        meta=_meta(),
    )


@router.get(
    "/reports", response_model=SuccessResponse[list[ReportResponse]], summary="List generated reports"
)
async def list_reports(
    organization_id: UUID,
    reports: ReportSvc,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[ReportResponse]]:
    """Reports generated in this organization, newest first."""
    rows = await reports.list_for_org(organization_id, limit=limit, offset=offset)
    return SuccessResponse(
        message="Reports listed.",
        data=[ReportResponse.model_validate(row) for row in rows],
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
    """Build and store one report. A build failure is recorded, not raised."""
    created = await reports.generate(
        organization_id,
        kind=body.kind,
        report_format=body.report_format,
        title=body.title,
        generated_by=str(caller),
    )
    await audit.record(
        organization_id,
        action=AuditAction.REPORT_GENERATED,
        entity_type="report",
        entity_id=created.id,
        actor_id=str(caller),
        summary=f"Generated a {body.kind!s} report.",
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
    """One report's metadata."""
    found = await reports.require_in_org(organization_id, report_id)
    return SuccessResponse(
        message="Report found.", data=ReportResponse.model_validate(found), meta=_meta()
    )


@router.get("/reports/{report_id}/download", summary="Download a report's content")
async def download_report(organization_id: UUID, report_id: UUID, reports: ReportSvc) -> Any:
    """A report's content, rendered as CSV, Markdown, or JSON.

    No route-level ``response_class``: CSV and Markdown return an
    explicit :class:`PlainTextResponse`, which FastAPI passes through
    unchanged, while JSON returns a plain :class:`SuccessResponse` for
    FastAPI's default JSON handling to serialise -- pinning the whole
    route to a single response class 500s the formats that aren't it,
    the same lesson every prior AI-IOS service's own copy of this route
    already carries forward.

    Raises:
        NotFoundError: If the report has not finished building.
    """
    found = await reports.require_in_org(organization_id, report_id)
    if report_status_of(found.status) is not ReportStatus.COMPLETED:
        raise NotFoundError(f"Report {report_id} has no completed content to download.")
    report_format = report_format_of(found.report_format)
    if report_format == ReportFormat.CSV:
        return PlainTextResponse(reports.to_csv(found.content), media_type="text/csv")
    if report_format == ReportFormat.MARKDOWN:
        return PlainTextResponse(
            reports.to_markdown(found.content, title=found.title), media_type="text/markdown"
        )
    return SuccessResponse(meta=_meta(), data=found.content, message="Report content read.")


@router.get(
    "/audit", response_model=SuccessResponse[list[AuditEntryResponse]], summary="List audit entries"
)
async def list_audit_entries(
    organization_id: UUID,
    audit: AuditSvc,
    action: Annotated[AuditAction | None, Query()] = None,
    entity_id: Annotated[UUID | None, Query()] = None,
    actor_id: Annotated[str | None, Query(max_length=255)] = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[AuditEntryResponse]]:
    """The append-only audit trail, newest first, matching a caller's filters."""
    rows = await audit.list_entries(
        organization_id, action=action, entity_id=entity_id, actor_id=actor_id, limit=limit, offset=offset
    )
    return SuccessResponse(
        message="Audit entries listed.",
        data=[AuditEntryResponse.model_validate(row) for row in rows],
        meta=_meta(),
    )


@router.get(
    "/audit/summary",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Summarise recent audit activity",
)
async def get_audit_summary(
    organization_id: UUID,
    audit: AuditSvc,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> SuccessResponse[dict[str, Any]]:
    """How much of each action has happened lately."""
    data = await audit.summary(organization_id, days=days)
    return SuccessResponse(message="Audit summary computed.", data=data, meta=_meta())


__all__ = ["router"]
