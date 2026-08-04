"""Dead-letter listing and manual retry (docs/055 "RETRY MANAGEMENT": "Manual Retry").

A supporting surface, not in docs/055's literal REST API list, but
necessary for "Dead Letter Queue"/"Manual Retry" to actually be operable
-- the same "extend the literal API list with the routes its own
feature section requires" precedent every prior AI-IOS service already
establishes.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, DeliverySvc
from app.models.enums import AuditAction
from app.schemas.notification import DeadLetterResponse, DeliveryResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/notifications/dead-letters", tags=["Delivery"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[list[DeadLetterResponse]], summary="List dead letters")
async def list_dead_letters(
    organization_id: UUID,
    delivery: DeliverySvc,
    resolved: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[DeadLetterResponse]]:
    """Dead letters in this organization."""
    rows = await delivery.list_dead_letters(organization_id, resolved=resolved, limit=limit, offset=offset)
    return SuccessResponse(
        message="Dead letters listed.",
        data=[DeadLetterResponse.model_validate(row) for row in rows],
        meta=_meta(),
    )


@router.post(
    "/{dead_letter_id}/retry",
    response_model=SuccessResponse[DeliveryResponse],
    summary="Manually retry a dead-lettered delivery",
)
async def retry_dead_letter(
    organization_id: UUID,
    dead_letter_id: UUID,
    delivery: DeliverySvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[DeliveryResponse]:
    """Manually retry one dead-lettered delivery ("Manual Retry")."""
    retried = await delivery.retry_dead_letter(organization_id, dead_letter_id, actor_id=str(caller))
    await audit.record(
        organization_id,
        action=AuditAction.NOTIFICATION_SENT,
        entity_type="dead_letter",
        entity_id=dead_letter_id,
        actor_id=str(caller),
        summary=f"Manually retried dead letter {dead_letter_id}.",
    )
    return SuccessResponse(
        message="Dead letter retried.", data=DeliveryResponse.model_validate(retried), meta=_meta()
    )


__all__ = ["router"]
