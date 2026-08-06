"""Delivery tracking (docs/057 "DELIVERY TRACKING", "REST APIs")."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from shared_core.logging.context import get_log_context

from app.api.deps import AuditSvc, CurrentUserId, DeliverySvc
from app.models.enums import AuditAction, DeliveryStatus
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.webhook import DeadLetterResponse, DeliveryResponse

router = APIRouter(prefix="/webhooks/deliveries", tags=["Deliveries"])
dead_letters_router = APIRouter(prefix="/webhooks/dead-letters", tags=["Dead Letters"])
"""A separate router (not a `/webhooks/deliveries/dead-letters` sub-path)
deliberately -- that shape would collide with `GET /webhooks/deliveries
/{delivery_id}` (a literal "dead-letters" segment would only ever reach
this route if it were registered strictly before the parameterized one,
the same router-ordering hazard notification-center-service and
api-gateway-service already hit once each in this build)."""


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[list[DeliveryResponse]], summary="List deliveries")
async def list_deliveries(
    organization_id: UUID,
    delivery: DeliverySvc,
    status_filter: Annotated[DeliveryStatus | None, Query(alias="status")] = None,
    endpoint_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[DeliveryResponse]]:
    """Deliveries in this organization, newest first."""
    rows = await delivery.list_deliveries(
        organization_id, status=status_filter, endpoint_id=endpoint_id, limit=limit, offset=offset
    )
    return SuccessResponse(
        message="Deliveries listed.",
        data=[DeliveryResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.get(
    "/{delivery_id}", response_model=SuccessResponse[DeliveryResponse], summary="Get a delivery"
)
async def get_delivery(
    organization_id: UUID, delivery_id: UUID, delivery: DeliverySvc
) -> SuccessResponse[DeliveryResponse]:
    """One delivery."""
    found = await delivery.get(organization_id, delivery_id)
    return SuccessResponse(
        message="Delivery found.", data=DeliveryResponse.model_validate(found), meta=_meta()
    )


@router.post(
    "/{delivery_id}/retry",
    response_model=SuccessResponse[DeliveryResponse],
    summary="Manually retry a delivery",
)
async def retry_delivery(
    organization_id: UUID,
    delivery_id: UUID,
    delivery: DeliverySvc,
    audit: AuditSvc,
    caller: CurrentUserId,
) -> SuccessResponse[DeliveryResponse]:
    """Force an immediate retry attempt, regardless of the scheduled backoff."""
    stored = await delivery.get(organization_id, delivery_id)
    outcome = await delivery.deliver(organization_id, stored)
    await audit.record(
        organization_id,
        action=AuditAction.DELIVERY_RETRIED,
        entity_type="delivery",
        entity_id=delivery_id,
        actor_id=str(caller),
        summary=f"Manually retried delivery {delivery_id}.",
    )
    return SuccessResponse(
        message="Delivery retried.",
        data=DeliveryResponse.model_validate(outcome.delivery),
        meta=_meta(),
    )


@dead_letters_router.get(
    "",
    response_model=SuccessResponse[list[DeadLetterResponse]],
    summary="List dead-lettered deliveries",
)
async def list_dead_letters(
    organization_id: UUID,
    delivery: DeliverySvc,
    replayed: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
) -> SuccessResponse[list[DeadLetterResponse]]:
    """Deliveries that exhausted their own retry policy, newest first."""
    rows = await delivery.list_dead_letters(organization_id, replayed=replayed, limit=limit)
    return SuccessResponse(
        message="Dead letters listed.",
        data=[DeadLetterResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@dead_letters_router.get(
    "/{dead_letter_id}",
    response_model=SuccessResponse[DeadLetterResponse],
    summary="Get a dead-lettered delivery",
)
async def get_dead_letter(
    organization_id: UUID, dead_letter_id: UUID, delivery: DeliverySvc
) -> SuccessResponse[DeadLetterResponse]:
    """One dead-lettered delivery."""
    found = await delivery.get_dead_letter(organization_id, dead_letter_id)
    return SuccessResponse(
        message="Dead letter found.", data=DeadLetterResponse.model_validate(found), meta=_meta()
    )


__all__ = ["dead_letters_router", "router"]
