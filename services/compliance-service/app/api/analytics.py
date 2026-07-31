"""Score, statistics, report, audit, and health endpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status
from shared_core.responses.success import SuccessResponse

from app.api.deps import (
    AuditSvc,
    CurrentUserId,
    ReportSvc,
    ScoringSvc,
    StatisticsSvc,
)
from app.models.enums import AuditAction, ReportFormat, ScoreScope
from app.schemas.compliance import (
    AuditResponse,
    ReportRequest,
    ReportResponse,
    StatisticResponse,
)

router = APIRouter(prefix="/compliance", tags=["analytics"])


@router.get(
    "/scores",
    response_model=SuccessResponse[dict],
    summary="Read the current compliance score",
)
async def current_score(
    organization_id: UUID,
    scoring: ScoringSvc,
    scope: ScoreScope = ScoreScope.OVERALL,
    scope_id: Annotated[str | None, Query(max_length=255)] = None,
) -> SuccessResponse[dict]:
    """The most recent score for one scope.

    Its ``breakdown`` carries ``coverage`` alongside the score, because a
    score without its coverage is the number people misread: 100% across
    4% of the estate is not compliance.
    """
    found = await scoring.current(organization_id, scope=scope, scope_id=scope_id)
    return SuccessResponse(
        data=found or {},
        message=(
            "Score read." if found else "No score has been computed yet; run an assessment first."
        ),
    )


@router.get(
    "/scores/history",
    response_model=SuccessResponse[dict],
    summary="Read a score's history and direction",
)
async def score_history(
    organization_id: UUID,
    scoring: ScoringSvc,
    scope: ScoreScope = ScoreScope.OVERALL,
    scope_id: Annotated[str | None, Query(max_length=255)] = None,
    days: Annotated[int, Query(ge=1, le=3_650)] = 365,
) -> SuccessResponse[dict]:
    """A scope's score over time, with a deadbanded trend."""
    return SuccessResponse(
        data=await scoring.history(organization_id, scope=scope, scope_id=scope_id, days=days),
        message="Score history read.",
    )


@router.get(
    "/scores/frameworks",
    response_model=SuccessResponse[list[dict]],
    summary="Read the newest score for every framework",
)
async def framework_scores(
    organization_id: UUID,
    scoring: ScoringSvc,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> SuccessResponse[list[dict]]:
    """One score per framework."""
    return SuccessResponse(
        data=await scoring.framework_scores(organization_id, limit=limit),
        message="Framework scores read.",
    )


@router.post(
    "/scores/assessments/{assessment_id}",
    response_model=SuccessResponse[dict],
    summary="Score one assessment",
)
async def score_assessment(
    organization_id: UUID,
    assessment_id: UUID,
    scoring: ScoringSvc,
    caller: CurrentUserId,
) -> SuccessResponse[dict]:
    """Recompute and store the scores for one run."""
    return SuccessResponse(
        data=await scoring.score_assessment(organization_id, assessment_id, actor_id=caller),
        message="Assessment scored.",
    )


@router.get(
    "/scores/assessments/{assessment_id}/targets",
    response_model=SuccessResponse[list[dict]],
    summary="Score every asset in one assessment",
)
async def score_targets(
    organization_id: UUID,
    assessment_id: UUID,
    scoring: ScoringSvc,
    caller: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
) -> SuccessResponse[list[dict]]:
    """Per-asset scores, worst first.

    The estate-wide number says whether there is a problem; this says
    where to go.
    """
    return SuccessResponse(
        data=await scoring.score_targets(
            organization_id, assessment_id, limit=limit, actor_id=caller
        ),
        message="Target scores computed.",
    )


@router.get(
    "/statistics",
    response_model=SuccessResponse[dict],
    summary="Read the compliance dashboard",
)
async def dashboard(organization_id: UUID, statistics: StatisticsSvc) -> SuccessResponse[dict]:
    """Everything a compliance dashboard needs, in one call."""
    return SuccessResponse(
        data=await statistics.dashboard(organization_id), message="Dashboard computed."
    )


@router.get(
    "/statistics/windows",
    response_model=SuccessResponse[list[StatisticResponse]],
    summary="Read rolled-up statistics windows",
)
async def statistics_windows(
    organization_id: UUID,
    statistics: StatisticsSvc,
    limit: Annotated[int, Query(ge=1, le=365)] = 30,
) -> SuccessResponse[list[StatisticResponse]]:
    """Recent windows, newest first."""
    rows = await statistics.recent(organization_id, limit=limit)
    return SuccessResponse(
        data=[StatisticResponse.model_validate(one) for one in rows],
        message="Statistics windows listed.",
    )


@router.post(
    "/statistics/rollup",
    response_model=SuccessResponse[StatisticResponse],
    summary="Roll up a statistics window",
)
async def rollup(
    organization_id: UUID,
    statistics: StatisticsSvc,
    caller: CurrentUserId,
    hours: Annotated[int, Query(ge=1, le=8_760)] = 24,
) -> SuccessResponse[StatisticResponse]:
    """Compute one window. Idempotent by window start."""
    now = datetime.now(UTC)
    record = await statistics.rollup(
        organization_id,
        window_start=now - timedelta(hours=hours),
        window_end=now,
        actor_id=caller,
    )
    return SuccessResponse(
        data=StatisticResponse.model_validate(record), message="Window rolled up."
    )


@router.get(
    "/reports",
    response_model=SuccessResponse[list[ReportResponse]],
    summary="List generated reports",
)
async def list_reports(
    organization_id: UUID,
    reports: ReportSvc,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[ReportResponse]]:
    """Reports, newest first."""
    rows = await reports.list_reports(organization_id, limit=limit, offset=offset)
    return SuccessResponse(
        data=[ReportResponse.model_validate(one) for one in rows], message="Reports listed."
    )


@router.post(
    "/reports",
    response_model=SuccessResponse[ReportResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Generate a report",
)
async def generate_report(
    organization_id: UUID,
    body: ReportRequest,
    reports: ReportSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ReportResponse]:
    """Build a report and store it.

    A build failure comes back as a report row with ``status: failed``
    and an ``error``, not as a 500: somebody who asked for a report needs
    to be told what went wrong with it.
    """
    record = await reports.generate(
        organization_id,
        kind=body.kind,
        report_format=body.report_format,
        title=body.title,
        framework_id=body.framework_id,
        assessment_id=body.assessment_id,
        period_days=body.period_days,
        actor_id=caller,
    )
    await audit.record(
        organization_id,
        action=AuditAction.REPORT_GENERATED,
        entity_type="report",
        entity_id=record.id,
        entity_reference=record.title,
        actor_id=str(caller),
        succeeded=record.error is None,
        summary=f"Generated {str(body.kind)!r} report {record.title!r}.",
    )
    return SuccessResponse(data=ReportResponse.model_validate(record), message="Report generated.")


@router.get(
    "/reports/{report_id}",
    response_model=SuccessResponse[ReportResponse],
    summary="Read one report",
)
async def get_report(
    organization_id: UUID, report_id: UUID, reports: ReportSvc
) -> SuccessResponse[ReportResponse]:
    """One report, with its content."""
    found = await reports.get(organization_id, report_id)
    return SuccessResponse(data=ReportResponse.model_validate(found), message="Report read.")


@router.get(
    "/reports/{report_id}/download",
    summary="Download a report in its stored format",
    responses={200: {"content": {"text/csv": {}, "text/markdown": {}}}},
)
async def download_report(organization_id: UUID, report_id: UUID, reports: ReportSvc) -> Response:
    """Render a report as CSV or Markdown.

    Returns the raw document rather than an envelope, because the caller
    is a browser or a spreadsheet, not a JSON client.
    """
    found = await reports.get(organization_id, report_id)
    fmt = ReportFormat(str(found.report_format))
    if fmt is ReportFormat.CSV:
        return Response(
            content=reports.to_csv(found.content),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="report-{report_id}.csv"'},
        )
    if fmt is ReportFormat.MARKDOWN:
        return Response(
            content=reports.to_markdown(found.content, title=found.title),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="report-{report_id}.md"'},
        )
    return Response(
        content=json.dumps(found.content, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="report-{report_id}.json"'},
    )


@router.get(
    "/audit",
    response_model=SuccessResponse[list[AuditResponse]],
    summary="Read the compliance audit trail",
)
async def list_audit(
    organization_id: UUID,
    audit: AuditSvc,
    entity_type: Annotated[str | None, Query(max_length=64)] = None,
    entity_id: UUID | None = None,
    actor_id: Annotated[str | None, Query(max_length=255)] = None,
    days: Annotated[int, Query(ge=1, le=3_650)] = 90,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[AuditResponse]]:
    """Audit entries, newest first."""
    rows = await audit.list_entries(
        organization_id,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        since=datetime.now(UTC) - timedelta(days=days),
        limit=limit,
        offset=offset,
    )
    return SuccessResponse(
        data=[AuditResponse.model_validate(one) for one in rows], message="Audit trail read."
    )


@router.get(
    "/audit/summary",
    response_model=SuccessResponse[dict],
    summary="Summarise the audit trail",
)
async def audit_summary(
    organization_id: UUID,
    audit: AuditSvc,
    days: Annotated[int, Query(ge=1, le=3_650)] = 30,
) -> SuccessResponse[dict]:
    """How much of each action has happened lately."""
    return SuccessResponse(
        data=await audit.summary(organization_id, days=days), message="Audit summary computed."
    )
