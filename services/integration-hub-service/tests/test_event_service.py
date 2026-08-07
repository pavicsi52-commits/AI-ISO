"""EventService: connector event ingestion and routing (docs/058 "EVENT ROUTING").

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.

Routing rules are not owned by this service (see ``EventService.ingest``'s
own docstring) -- its own caller (the API layer, or a test here) supplies
``routes`` directly. These tests exercise the service's own wiring into
``app.routing.engine.resolve_routes`` (status derivation, ``routed_to``)
and its own persistence/listing, not the routing engine's matching rules
in depth (covered by the pure engine's own tests).
"""

from __future__ import annotations

import uuid

import pytest

from app.models.enums import EventRoutingStatus, EventSource
from app.services.event import EventService

pytestmark = pytest.mark.asyncio


class TestIngestRoutingOutcomes:
    async def test_no_routes_given_is_pending_with_empty_routed_to(
        self, event_service: EventService, organization_id: uuid.UUID
    ) -> None:
        event = await event_service.ingest(
            organization_id,
            connector_id=None,
            source=EventSource.INTERNAL,
            event_type="order.created",
            payload={},
            routes=[],
        )

        assert event.routing_status == EventRoutingStatus.PENDING
        assert event.routed_to == []

    async def test_routes_given_but_none_match_is_filtered(
        self, event_service: EventService, organization_id: uuid.UUID
    ) -> None:
        routes = [
            {
                "destination_kind": "slack",
                "filter_rules": [
                    {"field": "event_type", "operator": "eq", "value": "order.shipped"}
                ],
            }
        ]

        event = await event_service.ingest(
            organization_id,
            connector_id=None,
            source=EventSource.INTERNAL,
            event_type="order.created",
            payload={},
            routes=routes,
        )

        assert event.routing_status == EventRoutingStatus.FILTERED
        assert event.routed_to == []

    async def test_a_matching_route_is_routed_with_its_destination_kind(
        self, event_service: EventService, organization_id: uuid.UUID
    ) -> None:
        routes = [
            {
                "destination_kind": "slack",
                "filter_rules": [
                    {"field": "event_type", "operator": "eq", "value": "order.created"}
                ],
            }
        ]

        event = await event_service.ingest(
            organization_id,
            connector_id=None,
            source=EventSource.INTERNAL,
            event_type="order.created",
            payload={},
            routes=routes,
        )

        assert event.routing_status == EventRoutingStatus.ROUTED
        assert event.routed_to == ["slack"]

    async def test_multiple_matching_routes_are_all_included(
        self, event_service: EventService, organization_id: uuid.UUID
    ) -> None:
        routes = [
            {"destination_kind": "slack", "filter_rules": []},
            {"destination_kind": "email", "filter_rules": []},
            {
                "destination_kind": "pager",
                "filter_rules": [
                    {"field": "event_type", "operator": "eq", "value": "never-matches"}
                ],
            },
        ]

        event = await event_service.ingest(
            organization_id,
            connector_id=None,
            source=EventSource.INTERNAL,
            event_type="order.created",
            payload={},
            routes=routes,
        )

        assert event.routing_status == EventRoutingStatus.ROUTED
        assert set(event.routed_to) == {"slack", "email"}

    async def test_route_matching_can_use_the_events_own_payload_fields(
        self, event_service: EventService, organization_id: uuid.UUID
    ) -> None:
        routes = [
            {
                "destination_kind": "webhook",
                "filter_rules": [{"field": "severity", "operator": "eq", "value": "critical"}],
            }
        ]

        matching = await event_service.ingest(
            organization_id,
            connector_id=None,
            source=EventSource.INTERNAL,
            event_type="alert.raised",
            payload={"severity": "critical"},
            routes=routes,
        )
        non_matching = await event_service.ingest(
            organization_id,
            connector_id=None,
            source=EventSource.INTERNAL,
            event_type="alert.raised",
            payload={"severity": "info"},
            routes=routes,
        )

        assert matching.routing_status == EventRoutingStatus.ROUTED
        assert non_matching.routing_status == EventRoutingStatus.FILTERED

    async def test_route_matching_can_use_the_events_own_source(
        self, event_service: EventService, organization_id: uuid.UUID
    ) -> None:
        routes = [
            {
                "destination_kind": "internal-only",
                "filter_rules": [{"field": "source", "operator": "eq", "value": "webhook"}],
            }
        ]

        matching = await event_service.ingest(
            organization_id,
            connector_id=None,
            source=EventSource.WEBHOOK,
            event_type="ping",
            payload={},
            routes=routes,
        )
        non_matching = await event_service.ingest(
            organization_id,
            connector_id=None,
            source=EventSource.INTERNAL,
            event_type="ping",
            payload={},
            routes=routes,
        )

        assert matching.routing_status == EventRoutingStatus.ROUTED
        assert non_matching.routing_status == EventRoutingStatus.FILTERED


class TestIngestPersistence:
    async def test_persists_the_given_fields(
        self, event_service: EventService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()

        event = await event_service.ingest(
            organization_id,
            connector_id=connector.id,
            source=EventSource.MESSAGE_QUEUE,
            event_type="order.created",
            payload={"order_id": "abc"},
            routes=[],
            correlation_id="corr-1",
        )

        assert event.organization_id == organization_id
        assert event.connector_id == connector.id
        assert event.source == EventSource.MESSAGE_QUEUE
        assert event.event_type == "order.created"
        assert event.payload == {"order_id": "abc"}
        assert event.correlation_id == "corr-1"
        assert event.id is not None

    async def test_connector_id_can_be_none(
        self, event_service: EventService, organization_id: uuid.UUID
    ) -> None:
        event = await event_service.ingest(
            organization_id,
            connector_id=None,
            source=EventSource.INTERNAL,
            event_type="system.ping",
            payload={},
            routes=[],
        )

        assert event.connector_id is None


class TestListForOrg:
    async def test_filters_by_connector(
        self, event_service: EventService, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector_a = await make_connector(name="connector-a")
        connector_b = await make_connector(name="connector-b")
        event_a = await event_service.ingest(
            organization_id,
            connector_id=connector_a.id,
            source=EventSource.INTERNAL,
            event_type="a.event",
            payload={},
            routes=[],
        )
        await event_service.ingest(
            organization_id,
            connector_id=connector_b.id,
            source=EventSource.INTERNAL,
            event_type="b.event",
            payload={},
            routes=[],
        )

        rows = await event_service.list_for_org(organization_id, connector_id=connector_a.id)

        assert [row.id for row in rows] == [event_a.id]

    async def test_pagination_limit_and_offset(
        self, event_service: EventService, organization_id: uuid.UUID
    ) -> None:
        created = []
        for i in range(5):
            created.append(
                await event_service.ingest(
                    organization_id,
                    connector_id=None,
                    source=EventSource.INTERNAL,
                    event_type=f"event.{i}",
                    payload={},
                    routes=[],
                )
            )

        first_page = await event_service.list_for_org(organization_id, limit=2, offset=0)
        second_page = await event_service.list_for_org(organization_id, limit=2, offset=2)

        assert len(first_page) == 2
        assert len(second_page) == 2
        # Newest first -- pages must not overlap.
        assert {row.id for row in first_page}.isdisjoint({row.id for row in second_page})
        all_ids = {row.id for row in created}
        assert {row.id for row in first_page} <= all_ids
        assert {row.id for row in second_page} <= all_ids

    async def test_is_tenant_scoped(
        self, event_service: EventService, organization_id: uuid.UUID
    ) -> None:
        await event_service.ingest(
            organization_id,
            connector_id=None,
            source=EventSource.INTERNAL,
            event_type="order.created",
            payload={},
            routes=[],
        )

        rows = await event_service.list_for_org(uuid.uuid4())

        assert rows == []

    async def test_newest_first(
        self, event_service: EventService, organization_id: uuid.UUID
    ) -> None:
        first = await event_service.ingest(
            organization_id,
            connector_id=None,
            source=EventSource.INTERNAL,
            event_type="first",
            payload={},
            routes=[],
        )
        second = await event_service.ingest(
            organization_id,
            connector_id=None,
            source=EventSource.INTERNAL,
            event_type="second",
            payload={},
            routes=[],
        )

        rows = await event_service.list_for_org(organization_id)

        ids_in_order = [row.id for row in rows]
        assert ids_in_order.index(second.id) < ids_in_order.index(first.id)
