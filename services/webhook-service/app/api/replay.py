"""Replay management (docs/057 "REPLAY", "REST APIs")."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, status
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, ReplaySvc
from app.models.enums import AuditAction
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.webhook import ReplayCreateRequest, ReplayResponse

router = APIRouter(prefix="/webhooks/replay", tags=["Replay"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[list[ReplayResponse]], summary="List replay jobs")
async def list_replay_jobs(
    organization_id: UUID, replay: ReplaySvc
) -> SuccessResponse[list[ReplayResponse]]:
    """Replay jobs in this organization, newest first."""
    rows = await replay.list_jobs(organization_id)
    return SuccessResponse(
        message="Replay jobs listed.", data=[ReplayResponse.model_validate(r) for r in rows], meta=_meta()
    )


@router.get("/{job_id}", response_model=SuccessResponse[ReplayResponse], summary="Get a replay job")
async def get_replay_job(
    organization_id: UUID, job_id: UUID, replay: ReplaySvc
) -> SuccessResponse[ReplayResponse]:
    """One replay job."""
    found = await replay.get(organization_id, job_id)
    return SuccessResponse(
        message="Replay job found.", data=ReplayResponse.model_validate(found), meta=_meta()
    )


@router.get(
    "/{job_id}/preview", response_model=SuccessResponse[dict[str, Any]], summary="Preview a replay job"
)
async def preview_replay_job(
    organization_id: UUID, job_id: UUID, replay: ReplaySvc
) -> SuccessResponse[dict[str, Any]]:
    """How many events a replay job would replay, without replaying them."""
    result = await replay.preview(organization_id, job_id)
    return SuccessResponse(message="Replay preview computed.", data=result, meta=_meta())


@router.post(
    "",
    response_model=SuccessResponse[ReplayResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a replay job",
)
async def create_replay_job(
    organization_id: UUID,
    body: ReplayCreateRequest,
    replay: ReplaySvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[ReplayResponse]:
    """Register a new replay job.

    Raises:
        ValidationError: If the request's own fields don't match what
            its scope requires.
    """
    created = await replay.create(
        organization_id,
        scope=body.scope,
        event_id=body.event_id,
        endpoint_id=body.endpoint_id,
        subscription_id=body.subscription_id,
        date_range_start=body.date_range_start,
        date_range_end=body.date_range_end,
        dry_run=body.dry_run,
        requested_by=str(caller),
    )
    await audit.record(
        organization_id,
        action=AuditAction.REPLAY_STARTED,
        entity_type="replay_job",
        entity_id=created.id,
        actor_id=str(caller),
        summary=f"Created {created.scope!s} replay job.",
    )
    return SuccessResponse(
        message="Replay job created.", data=ReplayResponse.model_validate(created), meta=_meta()
    )


@router.post(
    "/{job_id}/run", response_model=SuccessResponse[ReplayResponse], summary="Run a replay job"
)
async def run_replay_job(
    organization_id: UUID, job_id: UUID, replay: ReplaySvc
) -> SuccessResponse[ReplayResponse]:
    """Execute a replay job: re-fan-out every matching event."""
    completed = await replay.run(organization_id, job_id)
    return SuccessResponse(
        message="Replay job run.", data=ReplayResponse.model_validate(completed), meta=_meta()
    )


__all__ = ["router"]
