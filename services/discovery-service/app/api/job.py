"""``/discovery/jobs``. Per docs/037 REST list."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from shared_core.logging.context import get_log_context
from shared_core.queue.producer import Producer
from shared_core.types.queue import QueueMessage

from app.api.deps import CurrentUserId, CurrentUserToken, JobSvc, get_queue_producer
from app.models.discovery_job import DiscoveryJob
from app.schemas.job import DiscoveryJobCreateRequest, DiscoveryJobResponse
from app.schemas.response import ResponseMeta, SuccessResponse
from app.workers.discovery_worker import DISCOVERY_QUEUE_NAME

router = APIRouter(prefix="/discovery/jobs", tags=["Jobs"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


def job_to_response(job: DiscoveryJob) -> DiscoveryJobResponse:
    return DiscoveryJobResponse(
        id=job.id,
        organization_id=job.organization_id,
        profile_id=job.profile_id,
        schedule_id=job.schedule_id,
        mode=job.mode,
        status=job.status,
        triggered_by=job.triggered_by,
        total_targets=job.total_targets,
        succeeded_targets=job.succeeded_targets,
        failed_targets=job.failed_targets,
        discovered_asset_count=job.discovered_asset_count,
        discovered_relationship_count=job.discovered_relationship_count,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_summary=job.error_summary,
    )


@router.get("", response_model=SuccessResponse[list[DiscoveryJobResponse]])
async def list_jobs(
    organization_id: UUID, jobs: JobSvc, _caller: CurrentUserId
) -> SuccessResponse[list[DiscoveryJobResponse]]:
    """List every discovery job for *organization_id*."""
    records = await jobs.list_for_org(organization_id)
    return SuccessResponse(
        message="Discovery jobs retrieved.",
        data=[job_to_response(record) for record in records],
        meta=_meta(),
    )


@router.get("/{job_id}", response_model=SuccessResponse[DiscoveryJobResponse])
async def get_job(
    job_id: UUID, jobs: JobSvc, _caller: CurrentUserId
) -> SuccessResponse[DiscoveryJobResponse]:
    """Return one discovery job's status and result summary.

    Raises:
        NotFoundError: If no such job exists.
    """
    job = await jobs.get_by_id(job_id)
    return SuccessResponse(
        message="Discovery job retrieved.", data=job_to_response(job), meta=_meta()
    )


@router.post("", response_model=SuccessResponse[DiscoveryJobResponse], status_code=202)
async def create_job(
    body: DiscoveryJobCreateRequest,
    jobs: JobSvc,
    caller_id: CurrentUserId,
    caller_token: CurrentUserToken,
    producer: Annotated[Producer, Depends(get_queue_producer)],
) -> SuccessResponse[DiscoveryJobResponse]:
    """Queue a new discovery job, re-running *profile_id*'s currently
    registered targets ("Job Registration").
    """
    job = await jobs.create_job(
        organization_id=body.organization_id,
        profile_id=body.profile_id,
        mode=body.mode,
        triggered_by=caller_id,
    )
    message: QueueMessage = {"job_id": str(job.id), "caller_token": caller_token}
    await producer.publish(DISCOVERY_QUEUE_NAME, message)
    return SuccessResponse(message="Discovery job queued.", data=job_to_response(job), meta=_meta())


@router.delete("/{job_id}", response_model=SuccessResponse[DiscoveryJobResponse])
async def cancel_job(
    job_id: UUID, jobs: JobSvc, _caller: CurrentUserId
) -> SuccessResponse[DiscoveryJobResponse]:
    """Cancel a queued or running discovery job.

    Raises:
        NotFoundError: If no such job exists.
        ConflictError: If the job has already finished.
    """
    job = await jobs.cancel(job_id)
    return SuccessResponse(
        message="Discovery job cancelled.", data=job_to_response(job), meta=_meta()
    )


__all__ = ["job_to_response", "router"]
