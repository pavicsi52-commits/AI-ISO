"""``POST /projects/export``, plus the job-status endpoint docs/034's own
"EXPORT" functional section requires ("Background Processing" implies
polling) but its literal REST list doesn't separately enumerate.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context
from shared_core.queue.producer import Producer
from shared_core.types.queue import QueueMessage

from app.api.deps import CurrentUserId, ExportSvc, get_queue_producer
from app.models.project_export_job import ProjectExportJob
from app.schemas.import_export import ExportJobResponse, ExportRequest
from app.schemas.response import ResponseMeta, SuccessResponse
from app.workers.export_worker import EXPORT_QUEUE_NAME

router = APIRouter(prefix="/projects/export", tags=["Export"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


async def _to_response(job: ProjectExportJob, exports: ExportSvc) -> ExportJobResponse:
    download_url = await exports.download_url(job) if job.result_storage_key is not None else None
    return ExportJobResponse(
        job_id=job.id,
        status=job.status,
        target_format=job.target_format,
        total_rows=job.total_rows,
        download_url=download_url,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


def _filter_criteria(body: ExportRequest) -> dict[str, Any]:
    criteria: dict[str, Any] = {"organization_id": str(body.organization_id)}
    if body.status is not None:
        criteria["status"] = body.status
    if body.category is not None:
        criteria["category"] = body.category
    if body.tags:
        criteria["tags"] = body.tags
    return criteria


@router.post("", response_model=SuccessResponse[ExportJobResponse], status_code=202)
async def start_export(
    body: ExportRequest,
    exports: ExportSvc,
    current_user_id: CurrentUserId,
    producer: Annotated[Producer, Depends(get_queue_producer)],
) -> SuccessResponse[ExportJobResponse]:
    """Queue a bulk project-export job ("Filtered Export")."""
    job = await exports.create_job(
        current_user_id, target_format=body.target_format, filter_criteria=_filter_criteria(body)
    )
    message: QueueMessage = {"job_id": str(job.id)}
    await producer.publish(EXPORT_QUEUE_NAME, message)
    data = await _to_response(job, exports)
    return SuccessResponse(message="Export job queued.", data=data, meta=_meta())


@router.get("/{job_id}", response_model=SuccessResponse[ExportJobResponse])
async def get_export_job(
    job_id: UUID, exports: ExportSvc, _caller: CurrentUserId
) -> SuccessResponse[ExportJobResponse]:
    """Return one export job's status, including a download URL once ready."""
    job = await exports.get_job(job_id)
    data = await _to_response(job, exports)
    return SuccessResponse(message="Export job retrieved.", data=data, meta=_meta())


__all__ = ["router"]
