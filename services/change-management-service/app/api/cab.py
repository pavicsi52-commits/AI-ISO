"""Change Advisory Board review endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CabSvc, CurrentUserId
from app.models.enums import AuditAction
from app.schemas.change import CabResponse, CabScheduleRequest, CabVoteRequest, CabVoteResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(tags=["Change Advisory Board"])


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id."""
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post(
    "/changes/{change_id}/cab",
    response_model=SuccessResponse[CabResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Schedule a CAB review for a change",
)
async def schedule_review(
    organization_id: UUID,
    change_id: UUID,
    body: CabScheduleRequest,
    cab: CabSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[CabResponse]:
    """Open a CAB review for a change awaiting one."""
    created = await cab.schedule_review(
        organization_id,
        change_id,
        scheduled_at=body.scheduled_at,
        chair_id=body.chair_id,
        invited=body.invited,
        agenda=body.agenda,
        is_emergency_cab=body.is_emergency_cab,
        is_virtual=body.is_virtual,
    )
    await audit.record(
        organization_id,
        action=AuditAction.CAB_DECIDED,
        entity_type="change",
        entity_id=change_id,
        actor_id=str(caller),
        summary=f"CAB review scheduled for {body.scheduled_at.isoformat()}.",
    )
    return SuccessResponse(
        meta=_meta(), data=CabResponse.model_validate(created), message="CAB review scheduled."
    )


@router.get(
    "/changes/{change_id}/cab",
    response_model=SuccessResponse[CabResponse | None],
    summary="Read the CAB review for a change",
)
async def get_review_for_change(
    organization_id: UUID, change_id: UUID, cab: CabSvc
) -> SuccessResponse[CabResponse | None]:
    """The CAB review for one change, if one has been opened."""
    found = await cab.get_for_change(organization_id, change_id)
    data = CabResponse.model_validate(found) if found else None
    return SuccessResponse(
        meta=_meta(), data=data, message="Review found." if found else "No CAB review exists."
    )


@router.post(
    "/cab/{cab_id}/votes",
    response_model=SuccessResponse[CabVoteResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Cast a vote at a CAB review",
)
async def cast_vote(
    organization_id: UUID, cab_id: UUID, body: CabVoteRequest, cab: CabSvc
) -> SuccessResponse[CabVoteResponse]:
    """Record one board member's vote."""
    created = await cab.cast_vote(
        organization_id, cab_id, voter_id=body.voter_id, vote=body.vote, comment=body.comment
    )
    return SuccessResponse(
        meta=_meta(), data=CabVoteResponse.model_validate(created), message="Vote recorded."
    )


@router.get(
    "/cab/{cab_id}/votes",
    response_model=SuccessResponse[list[CabVoteResponse]],
    summary="List a CAB review's votes",
)
async def list_votes(
    organization_id: UUID, cab_id: UUID, cab: CabSvc
) -> SuccessResponse[list[CabVoteResponse]]:
    """Every vote cast at one review."""
    rows = await cab.list_votes(organization_id, cab_id)
    return SuccessResponse(
        meta=_meta(),
        data=[CabVoteResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} vote(s).",
    )


@router.post(
    "/cab/{cab_id}/close",
    response_model=SuccessResponse[CabResponse],
    summary="Tally a review's votes and close it",
)
async def close_meeting(
    organization_id: UUID, cab_id: UUID, cab: CabSvc, audit: AuditSvc, caller: CurrentUserId
) -> SuccessResponse[CabResponse]:
    """Tally votes and resolve the change the review was for."""
    updated = await cab.close_meeting(organization_id, cab_id)
    await audit.record(
        organization_id,
        action=AuditAction.CAB_DECIDED,
        entity_type="cab_review",
        entity_id=cab_id,
        actor_id=str(caller),
        summary=f"CAB review closed: outcome {updated.outcome!s}.",
    )
    return SuccessResponse(
        meta=_meta(), data=CabResponse.model_validate(updated), message="CAB review closed."
    )


__all__ = ["router"]
