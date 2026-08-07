"""HTTP tests for ``app/api/transformations.py`` (docs/058 "DATA TRANSFORMATION").

Neither ``GET``/``POST /integrations/transformations`` nor
``POST /integrations/transformations/{id}/apply`` declares a
``caller: CurrentUserId`` parameter, so none of them needs an
``Authorization`` header. Connectors are created directly through
``make_connector`` (the ``ConnectorService`` fixture, sharing the same
``db_session`` the ``client`` fixture's app is wired to) rather than through
the connector HTTP routes, since those *do* require a Bearer token and are
already covered elsewhere.

Real FastAPI app through ``httpx.ASGITransport`` (the ``client`` fixture),
real PostgreSQL underneath.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import HTTP_CREATED, HTTP_NOT_FOUND, HTTP_OK

pytestmark = pytest.mark.asyncio


class TestListTransformations:
    async def test_list_is_empty_before_any_registration(
        self, client: AsyncClient, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()

        resp = await client.get(
            "/integrations/transformations",
            params={"organization_id": str(organization_id), "connector_id": str(connector.id)},
        )

        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_list_returns_rules_in_priority_order(
        self, client: AsyncClient, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        await client.post(
            "/integrations/transformations",
            params={"organization_id": str(organization_id)},
            json={
                "connector_id": str(connector.id),
                "name": "low-priority",
                "kind": "enrichment",
                "priority": 50,
            },
        )
        await client.post(
            "/integrations/transformations",
            params={"organization_id": str(organization_id)},
            json={
                "connector_id": str(connector.id),
                "name": "high-priority",
                "kind": "enrichment",
                "priority": 5,
            },
        )

        resp = await client.get(
            "/integrations/transformations",
            params={"organization_id": str(organization_id), "connector_id": str(connector.id)},
        )

        assert resp.status_code == HTTP_OK
        names_in_order = [row["name"] for row in resp.json()["data"]]
        assert names_in_order.index("high-priority") < names_in_order.index("low-priority")

    async def test_list_returns_404_for_a_missing_connector(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/integrations/transformations",
            params={"organization_id": str(organization_id), "connector_id": str(uuid.uuid4())},
        )

        assert resp.status_code == HTTP_NOT_FOUND

    async def test_list_rejects_a_connector_from_another_organization(
        self, client: AsyncClient, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        other_org = uuid.uuid4()

        resp = await client.get(
            "/integrations/transformations",
            params={"organization_id": str(other_org), "connector_id": str(connector.id)},
        )

        assert resp.status_code == HTTP_NOT_FOUND


class TestCreateTransformation:
    async def test_create_returns_201_with_expected_shape(
        self, client: AsyncClient, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()

        resp = await client.post(
            "/integrations/transformations",
            params={"organization_id": str(organization_id)},
            json={
                "connector_id": str(connector.id),
                "name": "add-header",
                "kind": "field_mapping",
                "config": {"mapping": {"old": "new"}},
                "priority": 10,
            },
        )

        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["name"] == "add-header"
        assert data["kind"] == "field_mapping"
        assert data["config"] == {"mapping": {"old": "new"}}
        assert data["priority"] == 10
        assert data["connector_id"] == str(connector.id)
        assert data["enabled"] is True

    async def test_create_returns_404_for_an_unknown_connector(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/integrations/transformations",
            params={"organization_id": str(organization_id)},
            json={"connector_id": str(uuid.uuid4()), "name": "orphan-rule", "kind": "enrichment"},
        )

        assert resp.status_code == HTTP_NOT_FOUND

    async def test_create_persists_the_rule_findable_by_get(
        self, client: AsyncClient, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()

        created = await client.post(
            "/integrations/transformations",
            params={"organization_id": str(organization_id)},
            json={"connector_id": str(connector.id), "name": "persisted", "kind": "enrichment"},
        )
        assert created.status_code == HTTP_CREATED

        listed = await client.get(
            "/integrations/transformations",
            params={"organization_id": str(organization_id), "connector_id": str(connector.id)},
        )
        assert [row["name"] for row in listed.json()["data"]] == ["persisted"]


class TestCreateTransformationTenantIsolation:
    """Regression coverage for the cross-tenant transformation-hijack bug
    class found in sibling services (e.g. webhook-service's own
    ``/webhooks/transformations``): a caller must not be able to attach a
    transformation rule to a connector belonging to a *different*
    organization just because it knows (or guesses) the connector's id.

    ``create_transformation`` already calls ``connectors.get(organization_id,
    body.connector_id)`` first (``app/api/transformations.py``), which
    raises ``NotFoundError`` -- mapped to 404 -- whenever the connector does
    not belong to the caller's own organization. These tests confirm that
    guard actually holds, end to end over real HTTP.
    """

    async def test_create_rejects_a_connector_belonging_to_another_organization(
        self, client: AsyncClient, organization_id: uuid.UUID, make_connector
    ) -> None:
        victim_connector = await make_connector(name="victim-connector")
        attacker_org = uuid.uuid4()

        resp = await client.post(
            "/integrations/transformations",
            params={"organization_id": str(attacker_org)},
            json={
                "connector_id": str(victim_connector.id),
                "name": "cross-tenant-rule",
                "kind": "enrichment",
            },
        )

        assert resp.status_code == HTTP_NOT_FOUND

    async def test_the_hijack_attempt_does_not_create_any_row(
        self,
        client: AsyncClient,
        organization_id: uuid.UUID,
        make_connector,
        transformation_service,
    ) -> None:
        victim_connector = await make_connector(name="victim-connector-2")
        attacker_org = uuid.uuid4()

        resp = await client.post(
            "/integrations/transformations",
            params={"organization_id": str(attacker_org)},
            json={
                "connector_id": str(victim_connector.id),
                "name": "cross-tenant-rule-2",
                "kind": "enrichment",
            },
        )
        assert resp.status_code == HTTP_NOT_FOUND

        rows = await transformation_service.list_for_connector(victim_connector.id)
        assert rows == []


class TestApplyTransformation:
    async def test_apply_returns_the_transformed_result(
        self, client: AsyncClient, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await client.post(
            "/integrations/transformations",
            params={"organization_id": str(organization_id)},
            json={
                "connector_id": str(connector.id),
                "name": "rename",
                "kind": "field_mapping",
                "config": {"mapping": {"old_field": "new_field"}},
            },
        )
        transformation_id = created.json()["data"]["id"]

        resp = await client.post(
            f"/integrations/transformations/{transformation_id}/apply",
            params={"organization_id": str(organization_id)},
            json={"data": {"old_field": "value-123"}},
        )

        assert resp.status_code == HTTP_OK, resp.text
        assert resp.json()["data"]["result"] == {"new_field": "value-123"}

    async def test_apply_does_not_persist_a_new_transformation(
        self, client: AsyncClient, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await client.post(
            "/integrations/transformations",
            params={"organization_id": str(organization_id)},
            json={"connector_id": str(connector.id), "name": "enrich", "kind": "enrichment"},
        )
        transformation_id = created.json()["data"]["id"]

        await client.post(
            f"/integrations/transformations/{transformation_id}/apply",
            params={"organization_id": str(organization_id)},
            json={"data": {"a": 1}},
        )

        listed = await client.get(
            "/integrations/transformations",
            params={"organization_id": str(organization_id), "connector_id": str(connector.id)},
        )
        assert len(listed.json()["data"]) == 1

    async def test_apply_uses_the_rules_own_kind_and_config(
        self, client: AsyncClient, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await client.post(
            "/integrations/transformations",
            params={"organization_id": str(organization_id)},
            json={
                "connector_id": str(connector.id),
                "name": "enrich-with-default",
                "kind": "enrichment",
                "config": {"fields": {"added": "value"}},
            },
        )
        transformation_id = created.json()["data"]["id"]

        resp = await client.post(
            f"/integrations/transformations/{transformation_id}/apply",
            params={"organization_id": str(organization_id)},
            json={"data": {"existing": True}},
        )

        assert resp.json()["data"]["result"] == {"existing": True, "added": "value"}

    async def test_apply_returns_404_for_an_unknown_transformation(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/integrations/transformations/{uuid.uuid4()}/apply",
            params={"organization_id": str(organization_id)},
            json={"data": {}},
        )

        assert resp.status_code == HTTP_NOT_FOUND

    async def test_apply_returns_404_for_a_transformation_from_another_organization(
        self, client: AsyncClient, organization_id: uuid.UUID, make_connector
    ) -> None:
        connector = await make_connector()
        created = await client.post(
            "/integrations/transformations",
            params={"organization_id": str(organization_id)},
            json={"connector_id": str(connector.id), "name": "victim-rule", "kind": "enrichment"},
        )
        transformation_id = created.json()["data"]["id"]

        resp = await client.post(
            f"/integrations/transformations/{transformation_id}/apply",
            params={"organization_id": str(uuid.uuid4())},
            json={"data": {}},
        )

        assert resp.status_code == HTTP_NOT_FOUND
