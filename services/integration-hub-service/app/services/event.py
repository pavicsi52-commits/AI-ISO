"""Connector event ingestion and routing (docs/058 "EVENT ROUTING")."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.enums import EventRoutingStatus, EventSource
from app.models.event import ConnectorEvent
from app.repositories.event import ConnectorEventRepository
from app.routing import engine as routing_engine


class EventService:
    """Records one connector event and routes it to every matching destination.

    Routing rules live on ``Connector.config["routing"]["routes"]``
    (see ``Connector``'s own docstring for why no dedicated routing-rule
    table exists) -- this service reads them from the connector its
    caller already resolved, rather than owning a lookup of its own.
    """

    def __init__(self, events: ConnectorEventRepository) -> None:
        self._events = events

    async def ingest(
        self,
        organization_id: UUID,
        *,
        connector_id: UUID | None,
        source: EventSource,
        event_type: str,
        payload: dict[str, Any],
        routes: list[dict[str, Any]],
        correlation_id: str | None = None,
    ) -> ConnectorEvent:
        """Record one event and resolve which of *routes* it matches."""
        event_attributes = {
            "organization_id": str(organization_id),
            "event_type": event_type,
            "source": str(source),
            **payload,
        }
        resolved = routing_engine.resolve_routes(event_attributes, payload, routes)

        status = (
            EventRoutingStatus.ROUTED
            if resolved
            else (EventRoutingStatus.FILTERED if routes else EventRoutingStatus.PENDING)
        )
        return await self._events.create(
            ConnectorEvent(
                organization_id=organization_id,
                connector_id=connector_id,
                source=source,
                event_type=event_type,
                payload=payload,
                routing_status=status,
                routed_to=[destination.destination_kind for destination in resolved],
                correlation_id=correlation_id,
            )
        )

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        connector_id: UUID | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[ConnectorEvent]:
        """Events in this organization, newest first."""
        return await self._events.list_for_org(
            organization_id, connector_id=connector_id, limit=limit, offset=offset
        )


__all__ = ["EventService"]
