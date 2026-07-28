"""``/reports/schedule``, recipients, distribution, and ``/reports/archive``."""

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
    ExportRepo,
    JobSvc,
    ScheduleSvc,
)
from app.export.engine import FORMAT_SPECS, ExportedArtifact
from app.models.enums import (
    ArchiveStatus,
    AuditAction,
    DistributionChannel,
    DistributionStatus,
    ExportFormat,
)
from app.models.report_archive import ReportArchive
from app.models.report_distribution import ReportDistribution
from app.models.report_export import ReportExport
from app.models.report_recipient import ReportRecipient
from app.models.report_schedule import ReportSchedule
from app.schemas.delivery import (
    ArchiveRequest,
    ArchiveResponse,
    DistributeRequest,
    DistributionResponse,
    RecipientCreateRequest,
    RecipientResponse,
    ScheduleCreateRequest,
    ScheduleResponse,
    ScheduleUpdateRequest,
    ShareLinkResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/reports", tags=["Report Delivery"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def schedule_to_response(schedule: ReportSchedule) -> ScheduleResponse:
    """Map a schedule row onto its own response schema."""
    return ScheduleResponse(
        id=schedule.id,
        job_id=schedule.job_id,
        frequency=schedule.frequency,
        cron_expression=schedule.cron_expression,
        timezone=schedule.timezone,
        export_format=schedule.export_format,
        starts_at=schedule.starts_at,
        ends_at=schedule.ends_at,
        next_run_at=schedule.next_run_at,
        last_run_at=schedule.last_run_at,
        max_retries=schedule.max_retries,
        consecutive_failures=schedule.consecutive_failures,
        notify_on_failure=schedule.notify_on_failure,
        last_error=schedule.last_error,
        enabled=schedule.enabled,
    )


def recipient_to_response(recipient: ReportRecipient) -> RecipientResponse:
    """Map a recipient row onto its own response schema."""
    return RecipientResponse(
        id=recipient.id,
        job_id=recipient.job_id,
        channel=recipient.channel,
        target=recipient.target,
        export_format=recipient.export_format,
        headers=recipient.headers,
        enabled=recipient.enabled,
    )


def distribution_to_response(record: ReportDistribution) -> DistributionResponse:
    """Map a delivery row onto its own response schema.

    ``share_token`` is deliberately omitted -- see
    :class:`~app.schemas.delivery.DistributionResponse`.
    """
    return DistributionResponse(
        id=record.id,
        export_id=record.export_id,
        recipient_id=record.recipient_id,
        channel=record.channel,
        target=record.target,
        status=record.status,
        attempts=record.attempts,
        expires_at=record.expires_at,
        storage_uri=record.storage_uri,
        error_message=record.error_message,
        delivered_at=record.delivered_at,
    )


def archive_to_response(archive: ReportArchive) -> ArchiveResponse:
    """Map an archive row onto its own response schema."""
    return ArchiveResponse(
        id=archive.id,
        execution_id=archive.execution_id,
        job_id=archive.job_id,
        title=archive.title,
        export_format=archive.export_format,
        filename=archive.filename,
        content_type=archive.content_type,
        size_bytes=archive.size_bytes,
        checksum_sha256=archive.checksum_sha256,
        archive_version=archive.archive_version,
        status=archive.status,
        archived_at=archive.archived_at,
        retention_until=archive.retention_until,
        purge_reason=archive.purge_reason,
    )


def _artifact_from(record: ReportExport) -> ExportedArtifact:
    """Rebuild a deliverable artifact from a stored export row."""
    export_format = (
        record.export_format
        if isinstance(record.export_format, ExportFormat)
        else ExportFormat(record.export_format)
    )
    return ExportedArtifact(
        export_format=export_format,
        filename=record.filename,
        content_type=FORMAT_SPECS[export_format].content_type,
        content=record.content,
    )


@router.post("/schedule", response_model=SuccessResponse[ScheduleResponse], status_code=201)
async def create_schedule(
    body: ScheduleCreateRequest,
    schedules: ScheduleSvc,
    jobs: JobSvc,
    caller: CurrentUserId,
    audit: AuditSvc,
) -> SuccessResponse[ScheduleResponse]:
    """Schedule a report to run unattended.

    Raises:
        NotFoundError: If the report does not exist.
        ValidationError: If the cadence, cron expression, or time zone
            is invalid.
    """
    await jobs.get_by_id(body.report_id)
    schedule = await schedules.create(
        organization_id=body.organization_id,
        project_id=body.project_id,
        job_id=body.report_id,
        frequency=body.frequency,
        starts_at=body.starts_at,
        cron_expression=body.cron_expression,
        timezone_name=body.timezone,
        export_format=body.export_format,
        ends_at=body.ends_at,
        max_retries=body.max_retries,
        notify_on_failure=body.notify_on_failure,
    )
    await audit.record(
        organization_id=body.organization_id,
        action=AuditAction.SCHEDULE_CREATED,
        entity_type="ReportSchedule",
        entity_id=schedule.id,
        actor_id=caller,
    )
    return SuccessResponse(
        message="Report scheduled.", data=schedule_to_response(schedule), meta=_meta()
    )


@router.get("/schedules", response_model=SuccessResponse[list[ScheduleResponse]])
async def list_schedules(
    organization_id: UUID,
    schedules: ScheduleSvc,
    _caller: CurrentUserId,
    report_id: UUID | None = None,
) -> SuccessResponse[list[ScheduleResponse]]:
    """Schedules for an organization, or for one report."""
    records = (
        await schedules.list_for_job(report_id)
        if report_id is not None
        else await schedules.list_for_org(organization_id)
    )
    return SuccessResponse(
        message="Schedules retrieved.",
        data=[schedule_to_response(record) for record in records],
        meta=_meta(),
    )


@router.put("/schedules/{schedule_id}", response_model=SuccessResponse[ScheduleResponse])
async def update_schedule(
    schedule_id: UUID,
    body: ScheduleUpdateRequest,
    schedules: ScheduleSvc,
    caller: CurrentUserId,
    audit: AuditSvc,
) -> SuccessResponse[ScheduleResponse]:
    """Update a schedule, recomputing its next run.

    Raises:
        NotFoundError: If no such schedule exists.
        ValidationError: If the resulting configuration is invalid.
    """
    schedule = await schedules.update(
        schedule_id,
        frequency=body.frequency,
        cron_expression=body.cron_expression,
        timezone_name=body.timezone,
        export_format=body.export_format,
        ends_at=body.ends_at,
        enabled=body.enabled,
    )
    await audit.record(
        organization_id=schedule.organization_id,
        action=AuditAction.SCHEDULE_UPDATED,
        entity_type="ReportSchedule",
        entity_id=schedule.id,
        actor_id=caller,
    )
    return SuccessResponse(
        message="Schedule updated.", data=schedule_to_response(schedule), meta=_meta()
    )


@router.delete("/schedules/{schedule_id}", response_model=SuccessResponse[None])
async def delete_schedule(
    schedule_id: UUID, schedules: ScheduleSvc, caller: CurrentUserId, audit: AuditSvc
) -> SuccessResponse[None]:
    """Remove a schedule.

    Raises:
        NotFoundError: If no such schedule exists.
    """
    schedule = await schedules.get_by_id(schedule_id)
    await schedules.delete(schedule_id, deleted_by=caller)
    await audit.record(
        organization_id=schedule.organization_id,
        action=AuditAction.SCHEDULE_DELETED,
        entity_type="ReportSchedule",
        entity_id=schedule_id,
        actor_id=caller,
    )
    return SuccessResponse(message="Schedule deleted.", data=None, meta=_meta())


@router.get("/{report_id}/recipients", response_model=SuccessResponse[list[RecipientResponse]])
async def list_recipients(
    report_id: UUID, distribution: DistributionSvc, _caller: CurrentUserId
) -> SuccessResponse[list[RecipientResponse]]:
    """Standing recipients of one report."""
    records = await distribution.list_recipients(report_id)
    return SuccessResponse(
        message="Recipients retrieved.",
        data=[recipient_to_response(record) for record in records],
        meta=_meta(),
    )


@router.post(
    "/{report_id}/recipients",
    response_model=SuccessResponse[RecipientResponse],
    status_code=201,
)
async def add_recipient(
    report_id: UUID,
    body: RecipientCreateRequest,
    distribution: DistributionSvc,
    jobs: JobSvc,
    _caller: CurrentUserId,
) -> SuccessResponse[RecipientResponse]:
    """Register a standing recipient for a report.

    The target is validated for its channel here, so a typo'd webhook
    URL fails now rather than inside an unattended 03:00 run.

    Raises:
        NotFoundError: If the report does not exist.
        ValidationError: If the target is not valid for the channel.
    """
    await jobs.get_by_id(report_id)
    recipient = await distribution.add_recipient(
        organization_id=body.organization_id,
        project_id=body.project_id,
        job_id=report_id,
        channel=body.channel,
        target=body.target,
        export_format=body.export_format,
        headers=body.headers,
    )
    return SuccessResponse(
        message="Recipient added.", data=recipient_to_response(recipient), meta=_meta()
    )


@router.delete("/recipients/{recipient_id}", response_model=SuccessResponse[None])
async def remove_recipient(
    recipient_id: UUID, distribution: DistributionSvc, _caller: CurrentUserId
) -> SuccessResponse[None]:
    """Remove a standing recipient.

    Raises:
        NotFoundError: If no such recipient exists.
    """
    await distribution.remove_recipient(recipient_id)
    return SuccessResponse(message="Recipient removed.", data=None, meta=_meta())


@router.post(
    "/exports/{export_id}/distribute",
    response_model=SuccessResponse[DistributionResponse],
    status_code=201,
)
async def distribute_export(
    export_id: UUID,
    body: DistributeRequest,
    exports: ExportRepo,
    distribution: DistributionSvc,
    caller: CurrentUserId,
    audit: AuditSvc,
) -> SuccessResponse[DistributionResponse]:
    """Deliver one artifact over one channel now.

    Raises:
        NotFoundError: If no such artifact exists.
        ValidationError: If the target is not valid for the channel.
    """
    record = await exports.require_by_id(export_id)
    delivery = await distribution.deliver(
        record,
        _artifact_from(record),
        channel=body.channel,
        target=body.target,
        report_title=record.filename,
        headers=body.headers,
    )
    await audit.record(
        organization_id=record.organization_id,
        action=AuditAction.REPORT_DISTRIBUTED,
        entity_type="ReportDistribution",
        entity_id=delivery.id,
        actor_id=caller,
        context={"channel": str(body.channel), "status": str(delivery.status)},
    )
    return SuccessResponse(
        message="Delivery attempted.", data=distribution_to_response(delivery), meta=_meta()
    )


@router.post(
    "/exports/{export_id}/share", response_model=SuccessResponse[ShareLinkResponse], status_code=201
)
async def create_share_link(
    export_id: UUID,
    exports: ExportRepo,
    distribution: DistributionSvc,
    caller: CurrentUserId,
    audit: AuditSvc,
) -> SuccessResponse[ShareLinkResponse]:
    """Mint a time-limited shared link for one artifact.

    The token is returned **once, here**, to the caller who created it.
    It never appears in any listing endpoint, because it is a bearer
    credential for an otherwise unauthenticated recipient.

    Raises:
        NotFoundError: If no such artifact exists.
    """
    record = await exports.require_by_id(export_id)
    delivery = await distribution.deliver(
        record,
        _artifact_from(record),
        channel=DistributionChannel.SHARED_LINK,
        target="shared-link",
        report_title=record.filename,
    )
    await audit.record(
        organization_id=record.organization_id,
        action=AuditAction.REPORT_DISTRIBUTED,
        entity_type="ReportDistribution",
        entity_id=delivery.id,
        actor_id=caller,
        context={"channel": "shared_link"},
    )
    if delivery.share_token is None:  # pragma: no cover -- always minted
        raise NotFoundError("Share link could not be created.")
    return SuccessResponse(
        message="Share link created.",
        data=ShareLinkResponse(
            distribution_id=delivery.id,
            share_token=delivery.share_token,
            expires_at=delivery.expires_at,
        ),
        meta=_meta(),
    )


@router.get("/shared/{share_token}")
async def download_shared(share_token: str, distribution: DistributionSvc) -> Response:
    """Download an artifact via a shared link.

    Deliberately **unauthenticated**: the token is the credential, which
    is the entire point of a shareable link. Expiry is enforced on
    every redemption, so a leaked token stops working.

    Raises:
        NotFoundError: If the token is unknown.
        ConflictError: If the link has expired.
    """
    record = await distribution.resolve_share_token(share_token)
    return Response(
        content=record.content,
        media_type=record.content_type,
        headers={"Content-Disposition": f'attachment; filename="{record.filename}"'},
    )


@router.get(
    "/exports/{export_id}/distributions",
    response_model=SuccessResponse[list[DistributionResponse]],
)
async def list_export_distributions(
    export_id: UUID, distribution: DistributionSvc, _caller: CurrentUserId
) -> SuccessResponse[list[DistributionResponse]]:
    """Every delivery attempt for one artifact, failures included."""
    records = await distribution.list_for_export(export_id)
    return SuccessResponse(
        message="Delivery attempts retrieved.",
        data=[distribution_to_response(record) for record in records],
        meta=_meta(),
    )


@router.get("/distributions", response_model=SuccessResponse[list[DistributionResponse]])
async def list_distributions(
    organization_id: UUID,
    distribution: DistributionSvc,
    _caller: CurrentUserId,
    status: DistributionStatus | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> SuccessResponse[list[DistributionResponse]]:
    """Delivery attempts for an organization."""
    records = await distribution.list_for_org(organization_id, status=status, limit=limit)
    return SuccessResponse(
        message="Delivery attempts retrieved.",
        data=[distribution_to_response(record) for record in records],
        meta=_meta(),
    )


@router.get("/archive", response_model=SuccessResponse[list[ArchiveResponse]])
async def list_archive(
    organization_id: UUID,
    archive: ArchiveSvc,
    _caller: CurrentUserId,
    search: str | None = None,
    status: ArchiveStatus | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> SuccessResponse[list[ArchiveResponse]]:
    """Archived artifacts, optionally searched by title."""
    records = (
        await archive.search(organization_id, search, limit=limit)
        if search
        else await archive.list_for_org(organization_id, status=status, limit=limit)
    )
    return SuccessResponse(
        message="Archive retrieved.",
        data=[archive_to_response(record) for record in records],
        meta=_meta(),
    )


@router.post("/archive", response_model=SuccessResponse[ArchiveResponse], status_code=201)
async def archive_export(
    body: ArchiveRequest,
    exports: ExportRepo,
    archive: ArchiveSvc,
    _caller: CurrentUserId,
) -> SuccessResponse[ArchiveResponse]:
    """Archive one rendered artifact under a retention policy.

    Raises:
        NotFoundError: If no such artifact exists.
    """
    record = await exports.require_by_id(body.export_id)
    archived = await archive.archive_export(
        record, title=body.title, retention_days=body.retention_days
    )
    return SuccessResponse(
        message="Report archived.", data=archive_to_response(archived), meta=_meta()
    )


@router.get("/archive/{archive_id}/download")
async def download_archive(
    archive_id: UUID, archive: ArchiveSvc, caller: CurrentUserId, audit: AuditSvc
) -> Response:
    """Download an archived artifact, integrity-checked first.

    Raises:
        NotFoundError: If no such archive exists.
        ConflictError: If it is purged or fails its integrity check.
    """
    record = await archive.download(archive_id)
    await audit.record(
        organization_id=record.organization_id,
        action=AuditAction.REPORT_DOWNLOADED,
        entity_type="ReportArchive",
        entity_id=archive_id,
        actor_id=caller,
    )
    return Response(
        content=record.content,
        media_type=record.content_type,
        headers={"Content-Disposition": f'attachment; filename="{record.filename}"'},
    )


@router.post("/archive/{archive_id}/restore", response_model=SuccessResponse[ArchiveResponse])
async def restore_archive(
    archive_id: UUID, archive: ArchiveSvc, caller: CurrentUserId, audit: AuditSvc
) -> SuccessResponse[ArchiveResponse]:
    """Restore an archived artifact back into live exports.

    Raises:
        NotFoundError: If no such archive exists.
        ConflictError: If it is purged or fails its integrity check.
    """
    await archive.restore(archive_id)
    record = await archive.get_by_id(archive_id)
    await audit.record(
        organization_id=record.organization_id,
        action=AuditAction.ARCHIVE_RESTORED,
        entity_type="ReportArchive",
        entity_id=archive_id,
        actor_id=caller,
    )
    return SuccessResponse(
        message="Archive restored.", data=archive_to_response(record), meta=_meta()
    )


@router.delete("/archive/{archive_id}", response_model=SuccessResponse[ArchiveResponse])
async def purge_archive(
    archive_id: UUID,
    archive: ArchiveSvc,
    caller: CurrentUserId,
    audit: AuditSvc,
    reason: str | None = None,
) -> SuccessResponse[ArchiveResponse]:
    """Purge an archived artifact once its retention has elapsed.

    Raises:
        NotFoundError: If no such archive exists.
        ConflictError: If it is still within its retention window.
    """
    record = await archive.purge(archive_id, reason=reason)
    await audit.record(
        organization_id=record.organization_id,
        action=AuditAction.ARCHIVE_PURGED,
        entity_type="ReportArchive",
        entity_id=archive_id,
        actor_id=caller,
        reason=reason,
    )
    return SuccessResponse(
        message="Archive purged.", data=archive_to_response(record), meta=_meta()
    )


__all__ = [
    "archive_to_response",
    "distribution_to_response",
    "recipient_to_response",
    "router",
    "schedule_to_response",
]
