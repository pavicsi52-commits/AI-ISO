"""Postmortem endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, PostmortemSvc
from app.models.enums import AuditAction, PostmortemStatus
from app.schemas.incident import (
    ActionItemCreateRequest,
    ActionItemResponse,
    PostmortemResponse,
    PostmortemStartRequest,
    PostmortemTransitionRequest,
    PostmortemUpdateRequest,
)
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(tags=["Postmortems"])


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id."""
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post(
    "/incidents/{incident_id}/postmortem",
    response_model=SuccessResponse[PostmortemResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Begin a postmortem for an incident",
)
async def start_postmortem(
    organization_id: UUID,
    incident_id: UUID,
    body: PostmortemStartRequest,
    postmortems: PostmortemSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[PostmortemResponse]:
    """Begin a postmortem. Refuses until the incident has at least resolved."""
    created = await postmortems.start(organization_id, incident_id, author_id=body.author_id)
    await audit.record(
        organization_id,
        action=AuditAction.POSTMORTEM_CREATED,
        entity_type="incident",
        entity_id=incident_id,
        actor_id=str(caller),
        summary=f"Started a postmortem for incident {incident_id}.",
    )
    return SuccessResponse(
        meta=_meta(), data=PostmortemResponse.model_validate(created), message="Postmortem started."
    )


@router.get(
    "/incidents/{incident_id}/postmortem",
    response_model=SuccessResponse[PostmortemResponse | None],
    summary="Read the postmortem for an incident",
)
async def get_postmortem_for_incident(
    organization_id: UUID, incident_id: UUID, postmortems: PostmortemSvc
) -> SuccessResponse[PostmortemResponse | None]:
    """The postmortem for one incident, if one has been started."""
    found = await postmortems.get_for_incident(organization_id, incident_id)
    data = PostmortemResponse.model_validate(found) if found else None
    return SuccessResponse(
        meta=_meta(),
        data=data,
        message="Postmortem found." if found else "No postmortem has been started.",
    )


@router.get(
    "/postmortems/{postmortem_id}",
    response_model=SuccessResponse[PostmortemResponse],
    summary="Read one postmortem",
)
async def get_postmortem(
    organization_id: UUID, postmortem_id: UUID, postmortems: PostmortemSvc
) -> SuccessResponse[PostmortemResponse]:
    """One postmortem."""
    found = await postmortems.get(organization_id, postmortem_id)
    return SuccessResponse(
        meta=_meta(), data=PostmortemResponse.model_validate(found), message="Postmortem read."
    )


@router.put(
    "/postmortems/{postmortem_id}",
    response_model=SuccessResponse[PostmortemResponse],
    summary="Edit a postmortem's content",
)
async def update_postmortem(
    organization_id: UUID,
    postmortem_id: UUID,
    body: PostmortemUpdateRequest,
    postmortems: PostmortemSvc,
) -> SuccessResponse[PostmortemResponse]:
    """Edit content. Refuses once published."""
    updated = await postmortems.update_content(
        organization_id,
        postmortem_id,
        executive_summary=body.executive_summary,
        timeline_summary=body.timeline_summary,
        root_cause_summary=body.root_cause_summary,
        impact_summary=body.impact_summary,
        lessons_learned=body.lessons_learned,
    )
    return SuccessResponse(
        meta=_meta(), data=PostmortemResponse.model_validate(updated), message="Postmortem updated."
    )


@router.put(
    "/postmortems/{postmortem_id}/transition",
    response_model=SuccessResponse[PostmortemResponse],
    summary="Move a postmortem through its lifecycle",
)
async def transition_postmortem(
    organization_id: UUID,
    postmortem_id: UUID,
    body: PostmortemTransitionRequest,
    postmortems: PostmortemSvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[PostmortemResponse]:
    """Change status. Approval refuses while action items remain unowned; publication is one-way."""
    updated = await postmortems.transition(
        organization_id, postmortem_id, target=body.status, actor_id=body.actor_id
    )
    if body.status is PostmortemStatus.PUBLISHED:
        await audit.record(
            organization_id,
            action=AuditAction.POSTMORTEM_APPROVED,
            entity_type="postmortem",
            entity_id=postmortem_id,
            actor_id=str(caller),
            summary=f"Published postmortem {postmortem_id}.",
        )
    return SuccessResponse(
        meta=_meta(),
        data=PostmortemResponse.model_validate(updated),
        message="Postmortem status changed.",
    )


@router.post(
    "/postmortems/{postmortem_id}/action-items",
    response_model=SuccessResponse[ActionItemResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Commit a follow-up action from a postmortem",
)
async def add_action_item(
    organization_id: UUID,
    postmortem_id: UUID,
    body: ActionItemCreateRequest,
    postmortems: PostmortemSvc,
) -> SuccessResponse[ActionItemResponse]:
    """Commit an action item."""
    created = await postmortems.add_action_item(
        organization_id,
        postmortem_id,
        title=body.title,
        description=body.description,
        owner_id=body.owner_id,
        due_at=body.due_at,
    )
    return SuccessResponse(
        meta=_meta(), data=ActionItemResponse.model_validate(created), message="Action item added."
    )


@router.get(
    "/postmortems/{postmortem_id}/action-items",
    response_model=SuccessResponse[list[ActionItemResponse]],
    summary="Read a postmortem's action items",
)
async def list_action_items(
    organization_id: UUID, postmortem_id: UUID, postmortems: PostmortemSvc
) -> SuccessResponse[list[ActionItemResponse]]:
    """Every action item committed in this postmortem."""
    rows = await postmortems.action_items(organization_id, postmortem_id)
    return SuccessResponse(
        meta=_meta(),
        data=[ActionItemResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} action item(s).",
    )


@router.post(
    "/action-items/{action_item_id}/complete",
    response_model=SuccessResponse[ActionItemResponse],
    summary="Mark an action item done",
)
async def complete_action_item(
    organization_id: UUID, action_item_id: UUID, postmortems: PostmortemSvc
) -> SuccessResponse[ActionItemResponse]:
    """Mark done."""
    updated = await postmortems.complete_action_item(organization_id, action_item_id)
    return SuccessResponse(
        meta=_meta(),
        data=ActionItemResponse.model_validate(updated),
        message="Action item completed.",
    )


__all__ = ["router"]
