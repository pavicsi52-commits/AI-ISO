"""``/reports`` -- saved reports, generation, exports, history, statistics."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Response
from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.context import get_log_context

from app.api.deps import (
    ArchiveSvc,
    AuditSvc,
    CurrentUserId,
    DistributionSvc,
    EventPublisherDep,
    ExecutionRepo,
    ExportRepo,
    GenerationSvc,
    JobSvc,
    StatisticsSvc,
)
from app.events.report_events import SOURCE_SERVICE, ReportDownloadedEvent
from app.models.enums import AuditAction, ReportCategory
from app.models.report_execution import ReportExecution
from app.models.report_export import ReportExport
from app.models.report_history import ReportHistory
from app.models.report_job import ReportJob
from app.models.report_statistics import ReportStatistics
from app.schemas.report import (
    ExecutionResponse,
    ExportRequest,
    ExportSummary,
    GenerateResponse,
    HistoryResponse,
    ReportCreateRequest,
    ReportGenerateRequest,
    ReportResponse,
    ReportUpdateRequest,
    StatisticsResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/reports", tags=["Reports"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def job_to_response(job: ReportJob) -> ReportResponse:
    """Map a saved report row onto its own response schema."""
    return ReportResponse(
        id=job.id,
        organization_id=job.organization_id,
        project_id=job.project_id,
        template_id=job.template_id,
        name=job.name,
        description=job.description,
        category=job.category,
        report_type=job.report_type,
        default_format=job.default_format,
        parameter_values=job.parameter_values,
        filters=job.filters,
        enabled=job.enabled,
        owner_id=job.owner_id,
    )


def execution_to_response(execution: ReportExecution) -> ExecutionResponse:
    """Map an execution row onto its own response schema."""
    return ExecutionResponse(
        id=execution.id,
        job_id=execution.job_id,
        schedule_id=execution.schedule_id,
        status=execution.status,
        row_count=execution.row_count,
        section_count=execution.section_count,
        duration_ms=execution.duration_ms,
        error_message=execution.error_message,
        triggered_by=execution.triggered_by,
        started_at=execution.started_at,
        finished_at=execution.finished_at,
    )


def export_to_summary(record: ReportExport) -> ExportSummary:
    """Map an export row onto its summary, without the bytes."""
    return ExportSummary(
        id=record.id,
        execution_id=record.execution_id,
        export_format=record.export_format,
        filename=record.filename,
        content_type=record.content_type,
        size_bytes=record.size_bytes,
        checksum_sha256=record.checksum_sha256,
        download_count=record.download_count,
    )


def history_to_response(entry: ReportHistory) -> HistoryResponse:
    """Map a history row onto its own response schema."""
    return HistoryResponse(
        id=entry.id,
        job_id=entry.job_id,
        execution_id=entry.execution_id,
        event=entry.event,
        summary=entry.summary,
        details=entry.details,
        actor_id=entry.actor_id,
        occurred_at=entry.occurred_at,
    )


def statistics_to_response(snapshot: ReportStatistics) -> StatisticsResponse:
    """Map a statistics row onto its own response schema."""
    return StatisticsResponse(
        total_reports=snapshot.total_reports,
        total_executions=snapshot.total_executions,
        successful_executions=snapshot.successful_executions,
        failed_executions=snapshot.failed_executions,
        scheduled_executions=snapshot.scheduled_executions,
        total_downloads=snapshot.total_downloads,
        total_distributions=snapshot.total_distributions,
        failed_distributions=snapshot.failed_distributions,
        average_duration_ms=snapshot.average_duration_ms,
        popular_reports=snapshot.popular_reports,
        export_format_usage=snapshot.export_format_usage,
        template_usage=snapshot.template_usage,
        schedule_usage=snapshot.schedule_usage,
        distribution_usage=snapshot.distribution_usage,
        computed_at=snapshot.computed_at,
    )


@router.get("", response_model=SuccessResponse[list[ReportResponse]])
async def list_reports(
    organization_id: UUID,
    jobs: JobSvc,
    _caller: CurrentUserId,
    category: ReportCategory | None = None,
    enabled_only: bool = False,
) -> SuccessResponse[list[ReportResponse]]:
    """Every saved report for an organization."""
    records = await jobs.list_for_org(organization_id, category=category, enabled_only=enabled_only)
    return SuccessResponse(
        message="Reports retrieved.",
        data=[job_to_response(record) for record in records],
        meta=_meta(),
    )


@router.post("", response_model=SuccessResponse[ReportResponse], status_code=201)
async def create_report(
    body: ReportCreateRequest, jobs: JobSvc, caller: CurrentUserId, audit: AuditSvc
) -> SuccessResponse[ReportResponse]:
    """Create a saved report.

    Raises:
        ValidationError: If a filter clause is malformed.
    """
    job = await jobs.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        name=body.name,
        description=body.description,
        category=body.category,
        report_type=body.report_type,
        template_id=body.template_id,
        default_format=body.default_format,
        parameter_values=body.parameter_values,
        filters=body.filters,
        owner_id=caller,
    )
    await audit.record(
        organization_id=body.organization_id,
        action=AuditAction.REPORT_CREATED,
        entity_type="ReportJob",
        entity_id=job.id,
        actor_id=caller,
        reason=f"Report {body.name!r} created.",
    )
    return SuccessResponse(message="Report created.", data=job_to_response(job), meta=_meta())


@router.get("/history", response_model=SuccessResponse[list[HistoryResponse]])
async def list_history(
    organization_id: UUID,
    jobs: JobSvc,
    _caller: CurrentUserId,
    report_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> SuccessResponse[list[HistoryResponse]]:
    """Report activity, optionally narrowed to one report."""
    records = (
        await jobs.list_history(report_id, limit=limit)
        if report_id is not None
        else await jobs.list_org_history(organization_id, limit=limit)
    )
    return SuccessResponse(
        message="Report history retrieved.",
        data=[history_to_response(record) for record in records],
        meta=_meta(),
    )


@router.get("/statistics", response_model=SuccessResponse[StatisticsResponse])
async def get_statistics(
    organization_id: UUID,
    statistics: StatisticsSvc,
    _caller: CurrentUserId,
    recompute: bool = False,
) -> SuccessResponse[StatisticsResponse]:
    """An organization's own reporting analytics."""
    snapshot = (
        await statistics.recompute(organization_id)
        if recompute
        else await statistics.get_for_org(organization_id)
    )
    return SuccessResponse(
        message="Report statistics retrieved.",
        data=statistics_to_response(snapshot),
        meta=_meta(),
    )


@router.get("/{report_id}", response_model=SuccessResponse[ReportResponse])
async def get_report(
    report_id: UUID, jobs: JobSvc, _caller: CurrentUserId
) -> SuccessResponse[ReportResponse]:
    """Return one saved report.

    Raises:
        NotFoundError: If no such report exists.
    """
    job = await jobs.get_by_id(report_id)
    return SuccessResponse(message="Report retrieved.", data=job_to_response(job), meta=_meta())


@router.put("/{report_id}", response_model=SuccessResponse[ReportResponse])
async def update_report(
    report_id: UUID,
    body: ReportUpdateRequest,
    jobs: JobSvc,
    caller: CurrentUserId,
    audit: AuditSvc,
) -> SuccessResponse[ReportResponse]:
    """Update a saved report.

    Raises:
        NotFoundError: If no such report exists.
        ValidationError: If a filter clause is malformed.
    """
    job = await jobs.update(
        report_id,
        name=body.name,
        description=body.description,
        default_format=body.default_format,
        parameter_values=body.parameter_values,
        filters=body.filters,
        enabled=body.enabled,
    )
    await audit.record(
        organization_id=job.organization_id,
        action=AuditAction.REPORT_UPDATED,
        entity_type="ReportJob",
        entity_id=job.id,
        actor_id=caller,
    )
    return SuccessResponse(message="Report updated.", data=job_to_response(job), meta=_meta())


@router.delete("/{report_id}", response_model=SuccessResponse[None])
async def delete_report(
    report_id: UUID, jobs: JobSvc, caller: CurrentUserId, audit: AuditSvc
) -> SuccessResponse[None]:
    """Soft-delete a saved report.

    Raises:
        NotFoundError: If no such report exists.
    """
    job = await jobs.get_by_id(report_id)
    await jobs.delete(report_id, deleted_by=caller)
    await audit.record(
        organization_id=job.organization_id,
        action=AuditAction.REPORT_DELETED,
        entity_type="ReportJob",
        entity_id=report_id,
        actor_id=caller,
    )
    return SuccessResponse(message="Report deleted.", data=None, meta=_meta())


@router.post("/generate", response_model=SuccessResponse[GenerateResponse], status_code=201)
async def generate_report(
    body: ReportGenerateRequest,
    jobs: JobSvc,
    generation: GenerationSvc,
    distribution: DistributionSvc,
    archive: ArchiveSvc,
    caller: CurrentUserId,
    audit: AuditSvc,
) -> SuccessResponse[GenerateResponse]:
    """Generate a report now, optionally distributing and archiving it.

    Raises:
        NotFoundError: If the report or its template does not exist.
        ConflictError: If the template version is not approved.
        ValidationError: If parameters or filters are invalid.
    """
    job = await jobs.get_by_id(body.report_id)
    result = await generation.generate(
        job,
        export_formats=body.export_formats or None,
        parameter_overrides=body.parameter_values,
        filter_overrides=body.filters,
        triggered_by=caller,
        signed_by=body.signed_by,
        pdf_password=body.pdf_password,
    )

    distributed: list[UUID] = []
    if body.distribute and result.exports:
        deliveries = await distribution.deliver_to_recipients(
            result.exports[0], result.artifacts[0], job_id=job.id, report_title=job.name
        )
        distributed = [delivery.id for delivery in deliveries]

    archive_id: UUID | None = None
    if body.archive and result.exports:
        archived = await archive.archive_export(result.exports[0], title=job.name, job_id=job.id)
        archive_id = archived.id

    await audit.record(
        organization_id=job.organization_id,
        action=AuditAction.REPORT_GENERATED,
        entity_type="ReportExecution",
        entity_id=result.execution.id,
        actor_id=caller,
        reason=f"Generated {job.name!r}.",
        context={"degraded_sections": result.degraded_sections},
    )
    return SuccessResponse(
        message="Report generated.",
        data=GenerateResponse(
            execution=execution_to_response(result.execution),
            exports=[export_to_summary(record) for record in result.exports],
            degraded_sections=result.degraded_sections,
            distributions=distributed,
            archive_id=archive_id,
        ),
        meta=_meta(),
    )


@router.post("/export", response_model=SuccessResponse[ExportSummary], status_code=201)
async def export_execution(
    body: ExportRequest,
    executions: ExecutionRepo,
    jobs: JobSvc,
    generation: GenerationSvc,
    caller: CurrentUserId,
    audit: AuditSvc,
) -> SuccessResponse[ExportSummary]:
    """Re-export an existing execution in another format.

    Deliberately re-*renders* rather than converting stored bytes: a
    PDF cannot be turned into a spreadsheet, and the execution's own
    parameters are what make the new format faithful to the original
    run rather than an approximation of it.

    Raises:
        NotFoundError: If the execution does not exist.
        ConflictError: If the template version is no longer approved.
    """
    execution = await executions.require_by_id(body.execution_id)
    job = await jobs.get_by_id(execution.job_id)
    result = await generation.generate(
        job,
        export_formats=[body.export_format],
        parameter_overrides=execution.parameter_values,
        filter_overrides=execution.filters,
        triggered_by=caller,
        signed_by=body.signed_by,
        pdf_password=body.pdf_password,
    )
    await audit.record(
        organization_id=job.organization_id,
        action=AuditAction.REPORT_EXPORTED,
        entity_type="ReportExport",
        entity_id=result.exports[0].id if result.exports else None,
        actor_id=caller,
        context={"format": str(body.export_format)},
    )
    if not result.exports:  # pragma: no cover -- generate always stores one
        raise NotFoundError("Export produced no artifact.")
    return SuccessResponse(
        message="Report exported.", data=export_to_summary(result.exports[0]), meta=_meta()
    )


@router.get(
    "/executions/{execution_id}/exports",
    response_model=SuccessResponse[list[ExportSummary]],
)
async def list_execution_exports(
    execution_id: UUID, exports: ExportRepo, _caller: CurrentUserId
) -> SuccessResponse[list[ExportSummary]]:
    """Every artifact one execution produced."""
    records = await exports.list_for_execution(execution_id)
    return SuccessResponse(
        message="Exports retrieved.",
        data=[export_to_summary(record) for record in records],
        meta=_meta(),
    )


@router.get("/exports/{export_id}/download")
async def download_export(
    export_id: UUID,
    exports: ExportRepo,
    caller: CurrentUserId,
    audit: AuditSvc,
    publish_event: EventPublisherDep,
) -> Response:
    """Download one rendered artifact.

    Returns the real bytes with the artifact's own content type, so a
    browser or client handles a PDF as a PDF rather than as JSON.

    Raises:
        NotFoundError: If no such artifact exists.
    """
    record = await exports.require_by_id(export_id)
    await exports.record_download(export_id)
    await audit.record(
        organization_id=record.organization_id,
        action=AuditAction.REPORT_DOWNLOADED,
        entity_type="ReportExport",
        entity_id=export_id,
        actor_id=caller,
    )
    await publish_event(
        ReportDownloadedEvent(
            source_service=SOURCE_SERVICE,
            payload={"export_id": str(export_id), "format": str(record.export_format)},
        )
    )
    return Response(
        content=record.content,
        media_type=record.content_type,
        headers={"Content-Disposition": f'attachment; filename="{record.filename}"'},
    )


@router.post("/{report_id}/favorite", response_model=SuccessResponse[None], status_code=201)
async def favorite_report(
    report_id: UUID, jobs: JobSvc, caller: CurrentUserId
) -> SuccessResponse[None]:
    """Pin a report for the calling user; idempotent.

    Raises:
        NotFoundError: If no such report exists.
    """
    job = await jobs.get_by_id(report_id)
    await jobs.favorite(job.organization_id, caller, report_id)
    return SuccessResponse(message="Report favorited.", data=None, meta=_meta())


@router.delete("/{report_id}/favorite", response_model=SuccessResponse[None])
async def unfavorite_report(
    report_id: UUID, jobs: JobSvc, caller: CurrentUserId
) -> SuccessResponse[None]:
    """Unpin a report for the calling user."""
    removed = await jobs.unfavorite(caller, report_id)
    return SuccessResponse(
        message="Report unfavorited." if removed else "Report was not favorited.",
        data=None,
        meta=_meta(),
    )


@router.get("/favorites/mine", response_model=SuccessResponse[list[ReportResponse]])
async def list_my_favorites(
    organization_id: UUID, jobs: JobSvc, caller: CurrentUserId
) -> SuccessResponse[list[ReportResponse]]:
    """The reports the calling user has pinned."""
    records = await jobs.list_favorites(organization_id, caller)
    return SuccessResponse(
        message="Favorites retrieved.",
        data=[job_to_response(record) for record in records],
        meta=_meta(),
    )


__all__ = [
    "execution_to_response",
    "export_to_summary",
    "history_to_response",
    "job_to_response",
    "router",
    "statistics_to_response",
]
