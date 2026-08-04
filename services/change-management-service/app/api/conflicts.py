"""Scheduling conflict endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import ConflictSvc
from app.schemas.change import ConflictResolveRequest, ConflictResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(tags=["Conflicts"])


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id."""
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post(
    "/changes/{change_id}/conflicts/detect",
    response_model=SuccessResponse[list[ConflictResponse]],
    summary="Detect scheduling conflicts for a change",
)
async def detect_conflicts(
    organization_id: UUID, change_id: UUID, conflicts: ConflictSvc
) -> SuccessResponse[list[ConflictResponse]]:
    """Compare a change against every other scheduled change, recording new conflicts."""
    rows = await conflicts.detect_for_change(organization_id, change_id)
    return SuccessResponse(
        meta=_meta(),
        data=[ConflictResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} new conflict(s) detected.",
    )


@router.get(
    "/changes/{change_id}/conflicts",
    response_model=SuccessResponse[list[ConflictResponse]],
    summary="List a change's conflicts",
)
async def list_conflicts_for_change(
    organization_id: UUID, change_id: UUID, conflicts: ConflictSvc
) -> SuccessResponse[list[ConflictResponse]]:
    """Every conflict naming this change on either side."""
    rows = await conflicts.list_for_change(organization_id, change_id)
    return SuccessResponse(
        meta=_meta(),
        data=[ConflictResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} conflict(s).",
    )


@router.get(
    "/conflicts",
    response_model=SuccessResponse[list[ConflictResponse]],
    summary="List active conflicts",
)
async def list_active_conflicts(
    organization_id: UUID, conflicts: ConflictSvc
) -> SuccessResponse[list[ConflictResponse]]:
    """Every conflict still open across the organization."""
    rows = await conflicts.list_active(organization_id)
    return SuccessResponse(
        meta=_meta(),
        data=[ConflictResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} active conflict(s).",
    )


@router.post(
    "/conflicts/{conflict_id}/acknowledge",
    response_model=SuccessResponse[ConflictResponse],
    summary="Acknowledge a detected conflict",
)
async def acknowledge_conflict(
    organization_id: UUID, conflict_id: UUID, conflicts: ConflictSvc
) -> SuccessResponse[ConflictResponse]:
    """Acknowledge a conflict."""
    updated = await conflicts.acknowledge(organization_id, conflict_id)
    return SuccessResponse(
        meta=_meta(),
        data=ConflictResponse.model_validate(updated),
        message="Conflict acknowledged.",
    )


@router.post(
    "/conflicts/{conflict_id}/resolve",
    response_model=SuccessResponse[ConflictResponse],
    summary="Resolve a conflict",
)
async def resolve_conflict(
    organization_id: UUID, conflict_id: UUID, body: ConflictResolveRequest, conflicts: ConflictSvc
) -> SuccessResponse[ConflictResponse]:
    """Resolve a conflict."""
    updated = await conflicts.resolve(
        organization_id, conflict_id, resolved_by=body.resolved_by, note=body.note
    )
    return SuccessResponse(
        meta=_meta(), data=ConflictResponse.model_validate(updated), message="Conflict resolved."
    )


__all__ = ["router"]
