"""Synchronization, import/export, snapshots, statistics, and audit.

The operational surface: the endpoints an administrator uses rather
than the ones an application consumes.

**Import accepts base64 in a JSON body** rather than multipart. One body
shape carries all four formats, and a CSV can legitimately contain bytes
that are not valid UTF-8 inside a JSON string -- so the encoding is
explicit rather than hoping the payload survives the round trip.
"""

from __future__ import annotations

import base64
import binascii
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.context import get_log_context

from app.api.deps import (
    AuditSvc,
    CurrentUserId,
    GraphSvc,
    IoSvc,
    SnapshotSvc,
    StatisticsSvc,
    SyncSvc,
)
from app.models.enums import AuditAction, AuditOutcome, JobStatus, SyncSource, SyncStatus
from app.schemas.graph import (
    AuditEntryResponse,
    ChangeEntryResponse,
    DiffResponse,
    ExportJobResponse,
    ExportRequest,
    ImportJobResponse,
    ImportRequest,
    SnapshotRequest,
    SnapshotResponse,
    StatisticsResponse,
    SyncJobResponse,
    SyncRequest,
    VersionResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse
from app.services.graph_io import import_status_of

router = APIRouter(prefix="/graph", tags=["Operations"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


# ---- synchronization -------------------------------------------------


@router.post(
    "/sync",
    response_model=SuccessResponse[dict[str, object]],
    summary="Synchronize sources into the graph",
)
async def synchronize(
    organization_id: UUID,
    body: SyncRequest,
    sync: SyncSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[dict[str, object]]:
    """Pull the named sources -- or all of them -- into the graph.

    One source failing does not fail the run: each is recorded against
    its own job and the loop continues, because a caller syncing ten
    sources needs the other nine to proceed.
    """
    result = await sync.sync_all(
        organization_id,
        sources=body.sources,
        mode=body.mode,
        actor_id=caller,
        version_label=body.version_label,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.SYNCHRONIZED,
        entity_type="synchronization",
        actor_id=caller,
        context={
            "succeeded": result["succeeded"],
            "failed_sources": result["failed_sources"],
        },
    )
    return SuccessResponse(
        message=f"{result['succeeded']} sources synchronized.",
        data=result,
        meta=_meta(),
    )


@router.get(
    "/sync/history",
    response_model=SuccessResponse[list[SyncJobResponse]],
    summary="Synchronization history",
)
async def sync_history(
    organization_id: UUID,
    sync: SyncSvc,
    caller: CurrentUserId,
    source: SyncSource | None = None,
    sync_status: SyncStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> SuccessResponse[list[SyncJobResponse]]:
    """Return synchronization runs, most recent first."""
    del caller
    jobs = await sync.history(organization_id, source=source, status=sync_status, limit=limit)
    return SuccessResponse(
        message=f"Found {len(jobs)} runs.",
        data=[SyncJobResponse.model_validate(job) for job in jobs],
        meta=_meta(),
    )


@router.post(
    "/sync/{source}/reset",
    response_model=SuccessResponse[dict[str, str]],
    summary="Re-enable a disabled source",
)
async def reset_source(
    source: SyncSource,
    organization_id: UUID,
    sync: SyncSvc,
    caller: CurrentUserId,
) -> SuccessResponse[dict[str, str]]:
    """Clear a source's failure count and cursor.

    The cursor goes too: a source that broke badly enough to be disabled
    has usually also invalidated wherever its change feed had got to.
    """
    del caller
    job = await sync.reset_source(organization_id, source)
    return SuccessResponse(
        message=(
            f"Source {source} re-enabled."
            if job is not None
            else f"Source {source} has no history to reset."
        ),
        data={"source": str(source), "reset": str(job is not None)},
        meta=_meta(),
    )


# ---- import / export -------------------------------------------------


@router.post(
    "/import",
    response_model=SuccessResponse[ImportJobResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Import a graph payload",
)
async def import_graph(
    organization_id: UUID,
    body: ImportRequest,
    io: IoSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ImportJobResponse]:
    """Parse and, unless ``dry_run``, merge a payload into the graph.

    A dry run parses everything and writes nothing, which is how a
    malformed file is found before it half-lands rather than after.

    Raises:
        ValidationError: If ``content`` is not valid base64.
    """
    try:
        payload = base64.b64decode(body.content, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValidationError(f"The 'content' field must be base64-encoded: {exc}") from exc

    job = await io.import_graph(
        organization_id,
        payload=payload,
        filename=body.filename,
        graph_format=body.graph_format,
        dry_run=body.dry_run,
        actor_id=caller,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.IMPORTED,
        entity_type="import",
        entity_key=body.filename,
        outcome=(
            AuditOutcome.SUCCESS
            if import_status_of(job) is JobStatus.SUCCEEDED
            else AuditOutcome.FAILURE
        ),
        actor_id=caller,
        context={
            "dry_run": body.dry_run,
            "nodes": job.nodes_imported,
            "rejected": job.rejected,
        },
    )

    # A payload that could not be parsed at all is a client error, not a
    # created job. The job row is written and audited first so the
    # attempt is still on record -- but answering 201 to someone who
    # uploaded a corrupt file tells every client that checks only the
    # status code that their import worked.
    if import_status_of(job) is JobStatus.FAILED:
        raise ValidationError(
            f"The payload in {body.filename!r} could not be imported: {job.error}"
        )

    return SuccessResponse(
        message=(
            f"{'Validated' if body.dry_run else 'Imported'} "
            f"{job.nodes_imported} nodes, {job.rejected} rejected."
        ),
        data=ImportJobResponse.model_validate(job),
        meta=_meta(),
    )


@router.post(
    "/export",
    response_model=SuccessResponse[ExportJobResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Export the graph",
)
async def export_graph(
    organization_id: UUID,
    body: ExportRequest,
    io: IoSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ExportJobResponse]:
    """Render the graph into a downloadable payload."""
    job = await io.export_graph(
        organization_id,
        graph_format=body.graph_format,
        node_types=body.node_types,
        project_id=body.project_id,
        actor_id=caller,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.EXPORTED,
        entity_type="export",
        entity_key=job.filename,
        actor_id=caller,
        context={"nodes": job.node_count, "format": str(body.graph_format)},
    )
    return SuccessResponse(
        message=f"Exported {job.node_count} nodes to {job.filename}.",
        data=ExportJobResponse.model_validate(job),
        meta=_meta(),
    )


@router.get("/export/{export_id}/download", summary="Download an export")
async def download_export(export_id: UUID, io: IoSvc, caller: CurrentUserId) -> Response:
    """Return the rendered bytes, verified against their digest.

    A download that silently serves corrupted bytes is worse than one
    that refuses, and the recorded digest is the only thing that can
    tell the difference.

    Raises:
        NotFoundError: If no such export exists.
        ValidationError: If it holds no payload or fails verification.
    """
    del caller
    job = await io.get_export(export_id)
    verification = io.verify(job)
    if not verification["valid"] or job.payload is None:
        raise ValidationError(
            f"Export {export_id} cannot be served: "
            f"{verification.get('reason', 'checksum mismatch')}."
        )
    return Response(
        content=job.payload,
        media_type=job.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{job.filename}"',
            "X-Checksum-SHA256": job.checksum_sha256 or "",
        },
    )


# ---- snapshots and versions ------------------------------------------


@router.get(
    "/snapshots",
    response_model=SuccessResponse[list[SnapshotResponse]],
    summary="List snapshots",
)
async def list_snapshots(
    organization_id: UUID,
    snapshots: SnapshotSvc,
    caller: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> SuccessResponse[list[SnapshotResponse]]:
    """Return snapshots, newest first, without their payloads."""
    del caller
    rows = await snapshots.list_snapshots(organization_id, limit=limit)
    return SuccessResponse(
        message=f"Found {len(rows)} snapshots.",
        data=[SnapshotResponse.model_validate(row) for row in rows],
        meta=_meta(),
    )


@router.post(
    "/snapshots",
    response_model=SuccessResponse[SnapshotResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Capture a snapshot",
)
async def capture_snapshot(
    organization_id: UUID,
    body: SnapshotRequest,
    snapshots: SnapshotSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[SnapshotResponse]:
    """Serialise the whole organization graph into one restorable row."""
    record = await snapshots.capture(
        organization_id,
        label=body.label,
        description=body.description,
        snapshot_format=body.snapshot_format,
        actor_id=caller,
    )
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.SNAPSHOT_TAKEN,
        entity_type="snapshot",
        entity_key=body.label,
        actor_id=caller,
        context={"nodes": record.node_count},
    )
    return SuccessResponse(
        message=f"Snapshot {record.label!r} captured {record.node_count} nodes.",
        data=SnapshotResponse.model_validate(record),
        meta=_meta(),
    )


@router.post(
    "/snapshots/{snapshot_id}/restore",
    response_model=SuccessResponse[dict[str, object]],
    summary="Restore a snapshot",
)
async def restore_snapshot(
    snapshot_id: UUID,
    organization_id: UUID,
    snapshots: SnapshotSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[dict[str, object]]:
    """Replace the organization's graph with a snapshot.

    **Destructive.** Every node in the organization is purged first,
    because a merge would leave behind exactly what someone restoring is
    trying to remove. The payload's checksum is verified before anything
    is written.

    Raises:
        NotFoundError: If the snapshot does not exist.
        ConflictError: If it did not complete or fails its checksum.
    """
    result = await snapshots.restore(organization_id, snapshot_id, actor_id=caller)
    await audit.record(
        organization_id=organization_id,
        action=AuditAction.ADMINISTRATIVE,
        entity_type="snapshot_restore",
        entity_key=str(snapshot_id),
        actor_id=caller,
        context=result,
    )
    return SuccessResponse(
        message=(f"Restored {result['restored_nodes']} nodes, removing {result['removed_nodes']}."),
        data=result,
        meta=_meta(),
    )


@router.get(
    "/snapshots/{snapshot_id}/diff",
    response_model=SuccessResponse[DiffResponse],
    summary="Diff a snapshot against the current graph",
)
async def diff_snapshot(
    snapshot_id: UUID,
    organization_id: UUID,
    snapshots: SnapshotSvc,
    caller: CurrentUserId,
) -> SuccessResponse[DiffResponse]:
    """Answer "what has changed since this snapshot?"."""
    del caller
    diff = await snapshots.compare_to_current(organization_id, snapshot_id)
    return SuccessResponse(
        message=(
            "No changes since the snapshot."
            if diff.is_empty
            else f"{diff.as_dict()['total_changes']} changes since the snapshot."
        ),
        data=DiffResponse.model_validate(diff.as_dict()),
        meta=_meta(),
    )


@router.get(
    "/versions",
    response_model=SuccessResponse[list[VersionResponse]],
    summary="List graph versions",
)
async def list_versions(
    organization_id: UUID,
    snapshots: SnapshotSvc,
    caller: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> SuccessResponse[list[VersionResponse]]:
    """Return version markers, newest first."""
    del caller
    rows = await snapshots.list_versions(organization_id, limit=limit)
    return SuccessResponse(
        message=f"Found {len(rows)} versions.",
        data=[VersionResponse.model_validate(row) for row in rows],
        meta=_meta(),
    )


# ---- statistics, history, audit --------------------------------------


@router.get(
    "/statistics",
    response_model=SuccessResponse[StatisticsResponse],
    summary="Graph statistics",
)
async def statistics(
    organization_id: UUID,
    stats: StatisticsSvc,
    caller: CurrentUserId,
    recompute: bool = False,
) -> SuccessResponse[StatisticsResponse]:
    """Return the organization's graph statistics.

    Every figure is derived from the graph rather than incremented, so
    ``recompute`` produces numbers explainable by something you can go
    and count.
    """
    del caller
    record = await stats.refresh(organization_id) if recompute else await stats.get(organization_id)
    if record is None:
        record = await stats.refresh(organization_id)
    return SuccessResponse(
        message="Statistics retrieved.",
        data=StatisticsResponse.model_validate(record),
        meta=_meta(),
    )


@router.get(
    "/history",
    response_model=SuccessResponse[list[ChangeEntryResponse]],
    summary="Graph change history",
)
async def change_history(
    organization_id: UUID,
    graph: GraphSvc,
    caller: CurrentUserId,
    node_key: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 100,
) -> SuccessResponse[list[ChangeEntryResponse]]:
    """Return what changed, organization-wide or for one node."""
    del caller
    rows = await graph.history(organization_id, node_key=node_key, limit=limit)
    return SuccessResponse(
        message=f"Found {len(rows)} changes.",
        data=[ChangeEntryResponse.model_validate(row) for row in rows],
        meta=_meta(),
    )


@router.get(
    "/audit",
    response_model=SuccessResponse[list[AuditEntryResponse]],
    summary="Graph audit trail",
)
async def audit_trail(
    organization_id: UUID,
    audit: AuditSvc,
    caller: CurrentUserId,
    action: AuditAction | None = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
) -> SuccessResponse[list[AuditEntryResponse]]:
    """Return audited actions, most recent first.

    ``DENIED`` outcomes are included -- a refused Cypher statement is
    exactly what this trail exists to show.
    """
    del caller
    rows = await audit.list_for_org(organization_id, action=action, limit=limit)
    return SuccessResponse(
        message=f"Found {len(rows)} audit entries.",
        data=[AuditEntryResponse.model_validate(row) for row in rows],
        meta=_meta(),
    )


@router.get(
    "/audit/summary",
    response_model=SuccessResponse[dict[str, object]],
    summary="Audit counts by action and outcome",
)
async def audit_summary(
    organization_id: UUID,
    audit: AuditSvc,
    caller: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=5_000)] = 1_000,
) -> SuccessResponse[dict[str, object]]:
    """Return audit counts grouped by action and by outcome."""
    del caller
    return SuccessResponse(
        message="Audit summarised.",
        data=await audit.summarise(organization_id, limit=limit),
        meta=_meta(),
    )


__all__ = ["router"]
