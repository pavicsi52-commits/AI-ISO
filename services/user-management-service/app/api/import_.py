"""POST /users/import, GET /users/import/{job_id}, POST /users/import/{job_id}/rollback."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, UploadFile
from shared_core.logging.context import get_log_context
from shared_core.queue.producer import Producer
from shared_core.types.queue import QueueMessage

from app.api.deps import CurrentUserId, ImportSvc, get_queue_producer
from app.models.enums import ImportFormat
from app.models.import_job import UserImportJob
from app.schemas.import_export import ImportJobResponse
from app.schemas.response import ResponseMeta, SuccessResponse
from app.workers.import_worker import IMPORT_QUEUE_NAME

router = APIRouter(prefix="/users/import", tags=["Import"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def _to_response(job: UserImportJob) -> ImportJobResponse:
    return ImportJobResponse(
        job_id=job.id,
        status=job.status,
        source_format=job.source_format,
        preview_only=job.preview_only,
        total_rows=job.total_rows,
        processed_rows=job.processed_rows,
        succeeded_rows=job.succeeded_rows,
        failed_rows=job.failed_rows,
        duplicate_rows=job.duplicate_rows,
        error_report=job.error_report,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.post("", response_model=SuccessResponse[ImportJobResponse], status_code=202)
async def start_import(
    imports: ImportSvc,
    current_user_id: CurrentUserId,
    producer: Annotated[Producer, Depends(get_queue_producer)],
    file: UploadFile,
    source_format: Annotated[ImportFormat, Query()] = ImportFormat.CSV,
    preview_only: Annotated[bool, Query()] = False,
) -> SuccessResponse[ImportJobResponse]:
    """Upload a file and queue a bulk user-import job ("Bulk Import")."""
    content = await file.read()
    job = await imports.create_job(
        current_user_id,
        source_format=source_format,
        filename=file.filename or "import",
        content=content,
        preview_only=preview_only,
    )
    message: QueueMessage = {"job_id": str(job.id)}
    await producer.publish(IMPORT_QUEUE_NAME, message)
    return SuccessResponse(message="Import job queued.", data=_to_response(job), meta=_meta())


@router.get("/{job_id}", response_model=SuccessResponse[ImportJobResponse])
async def get_import_job(
    job_id: UUID, imports: ImportSvc, _caller: CurrentUserId
) -> SuccessResponse[ImportJobResponse]:
    """Return one import job's status ("Preview")."""
    job = await imports.get_job(job_id)
    return SuccessResponse(message="Import job retrieved.", data=_to_response(job), meta=_meta())


@router.post("/{job_id}/rollback", response_model=SuccessResponse[ImportJobResponse])
async def rollback_import_job(
    job_id: UUID, imports: ImportSvc, _caller: CurrentUserId
) -> SuccessResponse[ImportJobResponse]:
    """Roll back a completed import job ("Rollback")."""
    job = await imports.rollback_job(job_id)
    return SuccessResponse(message="Import job rolled back.", data=_to_response(job), meta=_meta())


__all__ = ["router"]
