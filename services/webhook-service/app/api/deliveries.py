"""Delivery tracking (docs/057 "DELIVERY TRACKING", "REST APIs")."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from shared_core.logging.context import get_log_context

from app.api.deps import DeliverySvc
from app.models.enums import DeliveryStatus
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.webhook import DeliveryResponse

router = APIRouter(prefix="/webhooks/deliveries", tags=["Deliveries"])


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
        message="Deliveries listed.", data=[DeliveryResponse.model_validate(r) for r in rows], meta=_meta()
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
    organization_id: UUID, delivery_id: UUID, delivery: DeliverySvc
) -> SuccessResponse[DeliveryResponse]:
    """Force an immediate retry attempt, regardless of the scheduled backoff."""
    stored = await delivery.get(organization_id, delivery_id)
    outcome = await delivery.deliver(organization_id, stored)
    return SuccessResponse(
        message="Delivery retried.", data=DeliveryResponse.model_validate(outcome.delivery), meta=_meta()
    )


__all__ = ["router"]
