"""Rollback endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, RollbackSvc
from app.models.enums import AuditAction
from app.schemas.change import (
    RollbackApproveRequest,
    RollbackCompleteRequest,
    RollbackFailRequest,
    RollbackPlanRequest,
    RollbackResponse,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(tags=["Rollback"])


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id."""
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post(
    "/changes/{change_id}/rollback",
    response_model=SuccessResponse[RollbackResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Prepare a rollback plan",
)
async def plan_rollback(
    organization_id: UUID, change_id: UUID, body: RollbackPlanRequest, rollback: RollbackSvc
) -> SuccessResponse[RollbackResponse]:
    """Prepare a rollback plan, without executing it yet."""
    created = await rollback.plan(
        organization_id,
        change_id,
        plan=body.plan,
        triggered_reason=body.triggered_reason,
        triggered_by=body.triggered_by,
    )
    return SuccessResponse(
        meta=_meta(), data=RollbackResponse.model_validate(created), message="Rollback planned."
    )


@router.get(
    "/changes/{change_id}/rollback",
    response_model=SuccessResponse[list[RollbackResponse]],
    summary="List a change's rollback attempts",
)
async def list_rollbacks(
    organization_id: UUID, change_id: UUID, rollback: RollbackSvc
) -> SuccessResponse[list[RollbackResponse]]:
    """Every rollback attempt for one change."""
    rows = await rollback.list_for_change(organization_id, change_id)
    return SuccessResponse(
        meta=_meta(),
        data=[RollbackResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} rollback attempt(s).",
    )


@router.post(
    "/rollback/{rollback_id}/approve",
    response_model=SuccessResponse[RollbackResponse],
    summary="Approve a planned rollback",
)
async def approve_rollback(
    organization_id: UUID, rollback_id: UUID, body: RollbackApproveRequest, rollback: RollbackSvc
) -> SuccessResponse[RollbackResponse]:
    """Approve a planned rollback."""
    updated = await rollback.approve(organization_id, rollback_id, approved_by=body.approved_by)
    return SuccessResponse(
        meta=_meta(), data=RollbackResponse.model_validate(updated), message="Rollback approved."
    )


@router.post(
    "/rollback/{rollback_id}/start",
    response_model=SuccessResponse[RollbackResponse],
    summary="Begin executing an approved rollback",
)
async def start_rollback(
    organization_id: UUID,
    rollback_id: UUID,
    rollback: RollbackSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[RollbackResponse]:
    """Begin executing an approved rollback."""
    updated = await rollback.start(organization_id, rollback_id, actor_id=caller)
    await audit.record(
        organization_id,
        action=AuditAction.ROLLBACK_STARTED,
        entity_type="change",
        entity_id=updated.change_id,
        actor_id=str(caller),
        summary=f"Rollback started: {updated.triggered_reason}",
    )
    return SuccessResponse(
        meta=_meta(), data=RollbackResponse.model_validate(updated), message="Rollback started."
    )


@router.post(
    "/rollback/{rollback_id}/complete",
    response_model=SuccessResponse[RollbackResponse],
    summary="Mark a rollback finished",
)
async def complete_rollback(
    organization_id: UUID,
    rollback_id: UUID,
    body: RollbackCompleteRequest,
    rollback: RollbackSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[RollbackResponse]:
    """Mark a rollback finished."""
    updated = await rollback.complete(
        organization_id, rollback_id, validation_summary=body.validation_summary
    )
    await audit.record(
        organization_id,
        action=AuditAction.ROLLBACK_COMPLETED,
        entity_type="change",
        entity_id=updated.change_id,
        actor_id=str(caller),
        summary=f"Rollback completed for change {updated.change_id}.",
    )
    return SuccessResponse(
        meta=_meta(), data=RollbackResponse.model_validate(updated), message="Rollback completed."
    )


@router.post(
    "/rollback/{rollback_id}/fail",
    response_model=SuccessResponse[RollbackResponse],
    summary="Mark a rollback attempt failed",
)
async def fail_rollback(
    organization_id: UUID, rollback_id: UUID, body: RollbackFailRequest, rollback: RollbackSvc
) -> SuccessResponse[RollbackResponse]:
    """Mark a rollback attempt failed."""
    updated = await rollback.fail(organization_id, rollback_id, reason=body.reason)
    return SuccessResponse(
        meta=_meta(),
        data=RollbackResponse.model_validate(updated),
        message="Rollback marked failed.",
    )


__all__ = ["router"]
