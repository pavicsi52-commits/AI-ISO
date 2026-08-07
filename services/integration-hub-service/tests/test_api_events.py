"""HTTP tests for ``app/api/events.py`` (docs/058 "EVENT ROUTING").

Neither ``GET``/``POST /integrations/events`` declares a
``caller: CurrentUserId`` parameter, so neither needs an ``Authorization``
header. Connectors (and their own ``config["routing"]["routes"]``) are set
up directly through ``make_connector``/``connector_service.configure``
(sharing the same ``db_session`` the ``client`` fixture's app is wired to)
rather than through the connector HTTP routes, since those *do* require a
Bearer token and are already covered elsewhere.

Real FastAPI app through ``httpx.ASGITransport`` (the ``client`` fixture),
real PostgreSQL underneath.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import HTTP_CREATED, HTTP_OK

pytestmark = pytest.mark.asyncio


class TestListEvents:
    async def test_list_filters_by_connector(
        self,
        client: AsyncClient,
        organization_id: uuid.UUID,
        make_connector,
    ) -> None:
        connector_a = await make_connector(name="connector-a")
        connector_b = await make_connector(name="connector-b")
        created_a = await client.post(
            "/integrations/events",
            params={"organization_id": str(organization_id)},
            json={
                "connector_id": str(connector_a.id),
                "event_type": "a.event",
                "source": "internal",
                "payload": {},
            },
        )
        assert created_a.status_code == HTTP_CREATED
        await client.post(
            "/integrations/events",
            params={"organization_id": str(organization_id)},
            json={
                "connector_id": str(connector_b.id),
                "event_type": "b.event",
                "source": "internal",
                "payload": {},
            },
        )

        resp = await client.get(
            "/integrations/events",
            params={"organization_id": str(organization_id), "connector_id": str(connector_a.id)},
        )

        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["id"] == created_a.json()["data"]["id"]

    async def test_list_respects_limit_and_offset(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        for i in range(4):
            resp = await client.post(
                "/integrations/events",
                params={"organization_id": str(organization_id)},
                json={"event_type": f"event.{i}", "source": "internal", "payload": {}},
            )
            assert resp.status_code == HTTP_CREATED

        first_page = await client.get(
            "/integrations/events",
            params={"organization_id": str(organization_id), "limit": 2, "offset": 0},
        )
        second_page = await client.get(
            "/integrations/events",
            params={"organization_id": str(organization_id), "limit": 2, "offset": 2},
        )

        assert len(first_page.json()["data"]) == 2
        assert len(second_page.json()["data"]) == 2
        first_ids = {row["id"] for row in first_page.json()["data"]}
        second_ids = {row["id"] for row in second_page.json()["data"]}
        assert first_ids.isdisjoint(second_ids)

    async def test_list_is_tenant_scoped(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/integrations/events",
            params={"organization_id": str(organization_id)},
            json={"event_type": "order.created", "source": "internal", "payload": {}},
        )
        assert created.status_code == HTTP_CREATED

        resp = await client.get(
            "/integrations/events", params={"organization_id": str(uuid.uuid4())}
        )

        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []


class TestIngestEvent:
    async def test_no_connector_id_succeeds_with_pending_status_and_empty_routes(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/integrations/events",
            params={"organization_id": str(organization_id)},
            json={"event_type": "system.ping", "source": "internal", "payload": {}},
        )

        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["connector_id"] is None
        assert data["routing_status"] == "pending"
        assert data["routed_to"] == []

    async def test_connector_with_no_routing_configured_is_pending(
        self, client: AsyncClient, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()  # config == {} -- never configured.

        resp = await client.post(
            "/integrations/events",
            params={"organization_id": str(organization_id)},
            json={
                "connector_id": str(connector.id),
                "event_type": "order.created",
                "source": "internal",
                "payload": {},
            },
        )

        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["routing_status"] == "pending"
        assert data["routed_to"] == []

    async def test_connectors_own_routing_rules_are_read_and_a_matching_route_routes(
        self, client: AsyncClient, organization_id: uuid.UUID, make_connector, connector_service
    ) -> None:
        connector = await make_connector()
        await connector_service.configure(
            organization_id,
            connector.id,
            config={
                "routing": {
                    "routes": [
                        {
                            "destination_kind": "slack",
                            "filter_rules": [
                                {"field": "event_type", "operator": "eq", "value": "order.created"}
                            ],
                        }
                    ]
                }
            },
        )

        resp = await client.post(
            "/integrations/events",
            params={"organization_id": str(organization_id)},
            json={
                "connector_id": str(connector.id),
                "event_type": "order.created",
                "source": "internal",
                "payload": {},
            },
        )

        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["routing_status"] == "routed"
        assert data["routed_to"] == ["slack"]

    async def test_connectors_own_routing_rules_that_do_not_match_are_filtered(
        self, client: AsyncClient, organization_id: uuid.UUID, make_connector, connector_service
    ) -> None:
        connector = await make_connector()
        await connector_service.configure(
            organization_id,
            connector.id,
            config={
                "routing": {
                    "routes": [
                        {
                            "destination_kind": "slack",
                            "filter_rules": [
                                {"field": "event_type", "operator": "eq", "value": "order.shipped"}
                            ],
                        }
                    ]
                }
            },
        )

        resp = await client.post(
            "/integrations/events",
            params={"organization_id": str(organization_id)},
            json={
                "connector_id": str(connector.id),
                "event_type": "order.created",
                "source": "internal",
                "payload": {},
            },
        )

        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["routing_status"] == "filtered"
        assert data["routed_to"] == []

    async def test_connector_config_with_a_non_dict_routing_value_is_treated_as_no_routes(
        self, client: AsyncClient, organization_id: uuid.UUID, make_connector, connector_service
    ) -> None:
        connector = await make_connector()
        await connector_service.configure(
            organization_id, connector.id, config={"routing": "not-a-dict"}
        )

        resp = await client.post(
            "/integrations/events",
            params={"organization_id": str(organization_id)},
            json={
                "connector_id": str(connector.id),
                "event_type": "order.created",
                "source": "internal",
                "payload": {},
            },
        )

        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["routing_status"] == "pending"
        assert data["routed_to"] == []

    async def test_returns_404_for_an_unknown_connector_id(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/integrations/events",
            params={"organization_id": str(organization_id)},
            json={
                "connector_id": str(uuid.uuid4()),
                "event_type": "order.created",
                "source": "internal",
                "payload": {},
            },
        )

        assert resp.status_code == 404

    async def test_rejects_a_connector_belonging_to_another_organization(
        self, client: AsyncClient, organization_id: uuid.UUID, make_connector
    ) -> None:
        victim_connector = await make_connector(name="victim-connector")
        attacker_org = uuid.uuid4()

        resp = await client.post(
            "/integrations/events",
            params={"organization_id": str(attacker_org)},
            json={
                "connector_id": str(victim_connector.id),
                "event_type": "order.created",
                "source": "internal",
                "payload": {},
            },
        )

        assert resp.status_code == 404

    async def test_correlation_id_is_persisted(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/integrations/events",
            params={"organization_id": str(organization_id)},
            json={
                "event_type": "order.created",
                "source": "internal",
                "payload": {},
                "correlation_id": "corr-42",
            },
        )

        assert resp.status_code == HTTP_CREATED
        assert resp.json()["data"]["correlation_id"] == "corr-42"

    async def test_payload_is_persisted(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/integrations/events",
            params={"organization_id": str(organization_id)},
            json={
                "event_type": "order.created",
                "source": "internal",
                "payload": {"order_id": "o-1"},
            },
        )

        assert resp.status_code == HTTP_CREATED
        assert resp.json()["data"]["payload"] == {"order_id": "o-1"}
