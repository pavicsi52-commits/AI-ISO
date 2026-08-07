"""Connector event ingestion and routing (docs/058 "EVENT ROUTING")."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from shared_core.logging.context import get_log_context

from app.api.deps import ConnectorSvc, EventSvc
from app.schemas.hub import ConnectorEventIngestRequest, ConnectorEventResponse
from app.schemas.response import ResponseMeta, SuccessResponse

router = APIRouter(prefix="/integrations/events", tags=["Events"])


def _meta() -> ResponseMeta:
    return ResponseMeta(request_id=get_log_context().request_id or "unknown")


@router.get("", response_model=SuccessResponse[list[ConnectorEventResponse]], summary="List events")
async def list_events(
    organization_id: UUID,
    events: EventSvc,
    connector_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=1_000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SuccessResponse[list[ConnectorEventResponse]]:
    """Events in this organization, newest first."""
    rows = await events.list_for_org(
        organization_id, connector_id=connector_id, limit=limit, offset=offset
    )
    return SuccessResponse(
        message="Events listed.",
        data=[ConnectorEventResponse.model_validate(r) for r in rows],
        meta=_meta(),
    )


@router.post(
    "",
    response_model=SuccessResponse[ConnectorEventResponse],
    status_code=201,
    summary="Raise an event",
)
async def ingest_event(
    organization_id: UUID,
    body: ConnectorEventIngestRequest,
    connectors: ConnectorSvc,
    events: EventSvc,
) -> SuccessResponse[ConnectorEventResponse]:
    """Record an event and route it to every one of its connector's own matching destinations.

    Confirms *body.connector_id* actually belongs to *organization_id*
    first, when one is given.
    """
    routes: list[dict[str, object]] = []
    if body.connector_id is not None:
        connector = await connectors.get(organization_id, body.connector_id)
        routing_config = connector.config.get("routing", {})
        routes = routing_config.get("routes", []) if isinstance(routing_config, dict) else []

    created = await events.ingest(
        organization_id,
        connector_id=body.connector_id,
        source=body.source,
        event_type=body.event_type,
        payload=body.payload,
        routes=routes,
        correlation_id=body.correlation_id,
    )
    return SuccessResponse(
        message="Event recorded.", data=ConnectorEventResponse.model_validate(created), meta=_meta()
    )


__all__ = ["router"]
