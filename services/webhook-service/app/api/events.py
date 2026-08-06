"""Event ingestion: internal events, incoming webhooks, and direct outgoing
delivery (docs/057 "WEBHOOK TYPES", "REST APIs").

``POST /webhooks/events`` is not in docs/057's own literal REST API
list -- it is the necessary extension that list otherwise omits: without
it, nothing could ever call this service to announce an *internal*
event (docs/057's own "EVENT SOURCES": Automation, Workflow Runtime,
Incident Management, etc.) for fan-out, since ``/webhooks/incoming`` is
specifically for signed *external* partner traffic. The same
"extend the literal list with the routes its own feature section
requires" precedent every prior AI-IOS service already establishes.
"""

from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from shared_core.logging.context import get_log_context

from app.api.deps import DeliverySvc, EventSvc, SignatureSvc
from app.config.settings import Settings, get_settings
from app.models.enums import EventSource
from app.schemas.response import ResponseMeta, SuccessResponse
from app.schemas.webhook import (
    DeliveryResponse,
    EventResponse,
    InternalEventRequest,
    OutgoingDeliveryRequest,
)

router = APIRouter(prefix="/webhooks", tags=["Events"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.post(
    "/events",
    response_model=SuccessResponse[EventResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Raise an internal event",
)
async def raise_internal_event(
    organization_id: UUID, body: InternalEventRequest, events: EventSvc, delivery: DeliverySvc
) -> SuccessResponse[EventResponse]:
    """Record an internally-raised event and fan it out to every matching subscription."""
    created = await events.ingest_internal(
        organization_id,
        source=body.source,
        event_type=body.event_type,
        payload=body.payload,
        severity=body.severity,
        status=body.status,
        tags=body.tags,
        labels=body.labels,
        idempotency_key=body.idempotency_key,
        correlation_id=body.correlation_id,
    )
    await delivery.fan_out(organization_id, created)
    return SuccessResponse(
        message="Event recorded.", data=EventResponse.model_validate(created), meta=_meta()
    )


@router.post(
    "/incoming",
    response_model=SuccessResponse[EventResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Receive an incoming webhook",
)
async def receive_incoming_webhook(
    organization_id: UUID,
    endpoint_id: UUID,
    request: Request,
    events: EventSvc,
    signatures: SignatureSvc,
    delivery: DeliverySvc,
    settings: Annotated[Settings, Depends(get_settings)],
    event_type: Annotated[str, Query()] = "webhook.received",
) -> SuccessResponse[EventResponse]:
    """Verify and record a webhook sent to us by an external partner.

    Raises:
        AuthenticationError: If the ``X-Webhook-Signature`` is missing,
            stale, or does not match any of the endpoint's own usable
            secrets.
    """
    body = await request.body()
    payload = json.loads(body) if body else {}
    created = await events.ingest_incoming(
        organization_id,
        endpoint_id=endpoint_id,
        event_type=event_type,
        body=body,
        payload=payload,
        headers=dict(request.headers),
        signature=request.headers.get("x-webhook-signature", ""),
        timestamp=int(request.headers.get("x-webhook-timestamp", "0")),
        nonce=request.headers.get("x-webhook-nonce", ""),
        signatures=signatures,
        tolerance_seconds=settings.service.signature_timestamp_tolerance_seconds,
        idempotency_key=request.headers.get("idempotency-key"),
        correlation_id=request.headers.get("x-correlation-id"),
    )
    await delivery.fan_out(organization_id, created)
    return SuccessResponse(
        message="Webhook received.", data=EventResponse.model_validate(created), meta=_meta()
    )


@router.post(
    "/outgoing",
    response_model=SuccessResponse[DeliveryResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Queue a direct outgoing delivery",
)
async def queue_outgoing_delivery(
    organization_id: UUID, body: OutgoingDeliveryRequest, events: EventSvc, delivery: DeliverySvc
) -> SuccessResponse[DeliveryResponse]:
    """Queue a delivery straight to one endpoint, bypassing subscription/filter resolution."""
    event = await events.ingest_internal(
        organization_id,
        source=EventSource.CUSTOM,
        event_type=body.event_type,
        payload=body.payload,
        idempotency_key=body.idempotency_key,
    )
    queued = await delivery.queue_direct(organization_id, event, endpoint_id=body.endpoint_id)
    return SuccessResponse(
        message="Delivery queued.", data=DeliveryResponse.model_validate(queued), meta=_meta()
    )


__all__ = ["router"]
