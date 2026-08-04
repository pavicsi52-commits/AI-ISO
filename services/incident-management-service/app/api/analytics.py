"""Statistics, generated reports, and the audit trail."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, status
from fastapi.responses import PlainTextResponse
from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, ReportSvc, StatisticsSvc
from app.models.enums import AuditAction, JobStatus, ReportFormat, job_status_of, report_format_of
from app.schemas.incident import (
    AuditEntryResponse,
    ReportGenerateRequest,
    ReportResponse,
    StatisticResponse,
    StatisticsRollupRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(tags=["Analytics"])


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id."""
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


# ---- statistics -----------------------------------------------------------------


@router.get(
    "/statistics/dashboard",
    response_model=SuccessResponse[dict[str, Any]],
    summary="Read the live dashboard snapshot",
)
async def get_dashboard(
    organization_id: UUID, statistics: StatisticsSvc
) -> SuccessResponse[dict[str, Any]]:
    """The snapshot a dashboard reads on load: open counts, the latest window."""
    data = await statistics.dashboard(organization_id)
    return SuccessResponse(meta=_meta(), data=data, message="Dashboard snapshot read.")


@router.post(
    "/statistics/rollup",
    response_model=SuccessResponse[StatisticResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Compute and store one window's statistics",
)
async def rollup_statistics(
    organization_id: UUID, body: StatisticsRollupRequest, statistics: StatisticsSvc
) -> SuccessResponse[StatisticResponse]:
    """Roll up one window. Idempotent by window start."""
    row = await statistics.rollup(
        organization_id, window_start=body.window_start, window_end=body.window_end
    )
    return SuccessResponse(
        meta=_meta(), data=StatisticResponse.model_validate(row), message="Window rolled up."
    )


@router.get(
    "/statistics/trend",
    response_model=SuccessResponse[list[StatisticResponse]],
    summary="Read recent statistics windows",
)
async def get_trend(
    organization_id: UUID,
    statistics: StatisticsSvc,
    since_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> SuccessResponse[list[StatisticResponse]]:
    """Recent windows, oldest first, for a trend chart."""
    rows = await statistics.trend(organization_id, since_days=since_days)
    return SuccessResponse(
        meta=_meta(),
        data=[StatisticResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} window(s).",
    )


# ---- reports --------------------------------------------------------------------


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
    """Build and store a report. A build failure is recorded, not raised."""
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
        meta=_meta(), data=ReportResponse.model_validate(created), message="Report generated."
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
    """Reports, newest first."""
    rows = await reports.list_for_org(organization_id, limit=limit, offset=offset)
    return SuccessResponse(
        meta=_meta(),
        data=[ReportResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} report(s).",
    )


@router.get(
    "/reports/{report_id}",
    response_model=SuccessResponse[ReportResponse],
    summary="Read one report",
)
async def get_report(
    organization_id: UUID, report_id: UUID, reports: ReportSvc
) -> SuccessResponse[ReportResponse]:
    """One report's metadata."""
    found = await reports.require_in_org(organization_id, report_id)
    return SuccessResponse(
        meta=_meta(), data=ReportResponse.model_validate(found), message="Report read."
    )


@router.get(
    "/reports/{report_id}/download",
    summary="Download a report's content",
    response_class=PlainTextResponse,
)
async def download_report(organization_id: UUID, report_id: UUID, reports: ReportSvc) -> Any:
    """A report's content, rendered as CSV, Markdown, or JSON.

    Raises:
        NotFoundError: If the report has not finished building, so there
            is nothing yet to render.
    """
    found = await reports.require_in_org(organization_id, report_id)
    if job_status_of(found.status) is not JobStatus.COMPLETED:
        raise NotFoundError(f"Report {report_id} has no completed content to download.")
    report_format = report_format_of(found.report_format)
    if report_format == ReportFormat.CSV:
        return PlainTextResponse(reports.to_csv(found.content), media_type="text/csv")
    if report_format == ReportFormat.MARKDOWN:
        return PlainTextResponse(
            reports.to_markdown(found.content, title=found.title), media_type="text/markdown"
        )
    return SuccessResponse(meta=_meta(), data=found.content, message="Report content read.")


# ---- audit trail ------------------------------------------------------------------


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
    """Audit entries, newest first, matching a caller's filters."""
    rows = await audit.list_entries(
        organization_id,
        action=action,
        entity_id=entity_id,
        actor_id=actor_id,
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(
        meta=_meta(),
        data=[AuditEntryResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} entr{'y' if len(rows) == 1 else 'ies'}.",
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
    return SuccessResponse(meta=_meta(), data=data, message="Audit summary computed.")


__all__ = ["router"]
