"""Priority escalation policy."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from shared_core.logging.context import get_log_context

from app.api.deps import PrioritySvc
from app.models.enums import JobPriority
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.scheduler import PriorityPolicyResponse, PriorityPolicySetRequest

router = APIRouter(prefix="/scheduler/priorities", tags=["Priorities"])


def _meta() -> ResponseMeta:
    """Response metadata carrying this request's id."""
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.put(
    "/{priority}",
    response_model=SuccessResponse[PriorityPolicyResponse],
    summary="Set the escalation policy for a priority band",
)
async def set_priority_policy(
    organization_id: UUID,
    priority: JobPriority,
    body: PriorityPolicySetRequest,
    priorities: PrioritySvc,
) -> SuccessResponse[PriorityPolicyResponse]:
    """Create or replace this organization's policy for one band."""
    saved = await priorities.set_policy(
        organization_id,
        priority,
        label=body.label,
        color=body.color,
        escalate_after_minutes=body.escalate_after_minutes,
        escalate_to=body.escalate_to,
    )
    return SuccessResponse(
        meta=_meta(),
        data=PriorityPolicyResponse.model_validate(saved),
        message="Priority policy set.",
    )


@router.get(
    "",
    response_model=SuccessResponse[list[PriorityPolicyResponse]],
    summary="List priority policies",
)
async def list_priority_policies(
    organization_id: UUID, priorities: PrioritySvc
) -> SuccessResponse[list[PriorityPolicyResponse]]:
    """Every band this organization has configured."""
    rows = await priorities.list_policies(organization_id)
    return SuccessResponse(
        meta=_meta(),
        data=[PriorityPolicyResponse.model_validate(one) for one in rows],
        message=f"{len(rows)} polic(y/ies).",
    )


__all__ = ["router"]
