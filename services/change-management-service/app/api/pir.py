"""Post-implementation review endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, PirSvc
from app.models.enums import AuditAction, PirStatus
from app.schemas.change import (
    PirActionItemCreateRequest,
    PirActionItemResponse,
    PirResponse,
    PirStartRequest,
    PirTransitionRequest,
    PirUpdateRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(tags=["Post-Implementation Review"])


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id."""
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post(
    "/changes/{change_id}/pir",
    response_model=SuccessResponse[PirResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Begin a post-implementation review",
)
async def start_review(
    organization_id: UUID,
    change_id: UUID,
    body: PirStartRequest,
    pir: PirSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[PirResponse]:
    """Begin a review. Refuses until the change has completed or rolled back."""
    created = await pir.start(organization_id, change_id, owner_id=body.owner_id)
    await audit.record(
        organization_id,
        action=AuditAction.PIR_COMPLETED,
        entity_type="change",
        entity_id=change_id,
        actor_id=str(caller),
        summary=f"Started a PIR for change {change_id}.",
    )
    return SuccessResponse(
        meta=_meta(), data=PirResponse.model_validate(created), message="PIR started."
    )


@router.get(
    "/changes/{change_id}/pir",
    response_model=SuccessResponse[PirResponse | None],
    summary="Read the review for a change",
)
async def get_review_for_change(
    organization_id: UUID, change_id: UUID, pir: PirSvc
) -> SuccessResponse[PirResponse | None]:
    """The review for one change, if one has been started."""
    found = await pir.get_for_change(organization_id, change_id)
    data = PirResponse.model_validate(found) if found else None
    return SuccessResponse(
        meta=_meta(), data=data, message="PIR found." if found else "No PIR has been started."
    )


@router.get(
    "/pir/{review_id}", response_model=SuccessResponse[PirResponse], summary="Read one review"
)
async def get_review(
    organization_id: UUID, review_id: UUID, pir: PirSvc
) -> SuccessResponse[PirResponse]:
    """One review."""
    found = await pir.get(organization_id, review_id)
    return SuccessResponse(
        meta=_meta(), data=PirResponse.model_validate(found), message="PIR read."
    )


@router.put(
    "/pir/{review_id}",
    response_model=SuccessResponse[PirResponse],
    summary="Edit a review's content",
)
async def update_review(
    organization_id: UUID, review_id: UUID, body: PirUpdateRequest, pir: PirSvc
) -> SuccessResponse[PirResponse]:
    """Edit content. Refuses once approved."""
    updated = await pir.update_content(
        organization_id,
        review_id,
        **body.model_dump(exclude_unset=True),
    )
    return SuccessResponse(
        meta=_meta(), data=PirResponse.model_validate(updated), message="PIR updated."
    )


@router.put(
    "/pir/{review_id}/transition",
    response_model=SuccessResponse[PirResponse],
    summary="Move a review through its lifecycle",
)
async def transition_review(
    organization_id: UUID,
    review_id: UUID,
    body: PirTransitionRequest,
    pir: PirSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[PirResponse]:
    """Change status. Approval refuses while any action item is unowned."""
    updated = await pir.transition(
        organization_id, review_id, target=body.status, actor_id=body.actor_id
    )
    if body.status is PirStatus.APPROVED:
        await audit.record(
            organization_id,
            action=AuditAction.PIR_COMPLETED,
            entity_type="pir",
            entity_id=review_id,
            actor_id=str(caller),
            summary=f"PIR {review_id} approved.",
        )
    return SuccessResponse(
        meta=_meta(), data=PirResponse.model_validate(updated), message="PIR status changed."
    )


@router.post(
    "/pir/{review_id}/action-items",
    response_model=SuccessResponse[PirActionItemResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Commit a follow-up action from a review",
)
async def add_action_item(
    organization_id: UUID, review_id: UUID, body: PirActionItemCreateRequest, pir: PirSvc
) -> SuccessResponse[PirActionItemResponse]:
    """Commit an action item."""
    created = await pir.add_action_item(
        organization_id,
        review_id,
        title=body.title,
        description=body.description,
        owner_id=body.owner_id,
        due_at=body.due_at,
    )
    return SuccessResponse(
        meta=_meta(),
        data=PirActionItemResponse.model_validate(created),
        message="Action item added.",
    )


@router.get(
    "/pir/{review_id}/action-items",
    response_model=SuccessResponse[list[PirActionItemResponse]],
    summary="Read a review's action items",
)
async def list_action_items(
    organization_id: UUID, review_id: UUID, pir: PirSvc
) -> SuccessResponse[list[PirActionItemResponse]]:
    """Every action item committed in this review."""
    rows = await pir.action_items(organization_id, review_id)
    return SuccessResponse(
        meta=_meta(),
        data=[PirActionItemResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} action item(s).",
    )


@router.post(
    "/pir-action-items/{action_item_id}/complete",
    response_model=SuccessResponse[PirActionItemResponse],
    summary="Mark an action item done",
)
async def complete_action_item(
    organization_id: UUID, action_item_id: UUID, pir: PirSvc
) -> SuccessResponse[PirActionItemResponse]:
    """Mark done."""
    updated = await pir.complete_action_item(organization_id, action_item_id)
    return SuccessResponse(
        meta=_meta(),
        data=PirActionItemResponse.model_validate(updated),
        message="Action item completed.",
    )


__all__ = ["router"]
