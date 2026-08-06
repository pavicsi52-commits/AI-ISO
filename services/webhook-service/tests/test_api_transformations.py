"""HTTP tests for /webhooks/transformations.

Neither route declares a ``caller: CurrentUserId`` parameter, so neither
needs an ``Authorization`` header. Both take ``organization_id`` as a query
parameter and verify the given ``endpoint_id`` actually belongs to that
organization before touching any transformation row -- a fix made in this
same change (see the ``TestTenantIsolation`` class below for why).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import FAKE_BACKEND_URL, HTTP_CREATED, HTTP_NOT_FOUND, HTTP_OK

pytestmark = pytest.mark.asyncio


async def _create_endpoint(
    client: AsyncClient, auth_headers, organization_id: uuid.UUID, name: str
) -> str:
    resp = await client.post(
        "/webhooks/endpoints",
        params={"organization_id": str(organization_id)},
        headers=auth_headers(uuid.uuid4()),
        json={"name": name, "url": f"{FAKE_BACKEND_URL}/echo"},
    )
    return resp.json()["data"]["id"]


class TestListTransformations:
    async def test_list_is_empty_before_any_registration(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(
            client, auth_headers, organization_id, "list-transform-endpoint"
        )
        resp = await client.get(
            "/webhooks/transformations",
            params={"organization_id": str(organization_id), "endpoint_id": endpoint_id},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_list_finds_a_created_rule_ordered_by_priority(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(
            client, auth_headers, organization_id, "find-transform-endpoint"
        )
        await client.post(
            "/webhooks/transformations",
            params={"organization_id": str(organization_id)},
            json={
                "endpoint_id": endpoint_id,
                "name": "low-priority",
                "kind": "field_removal",
                "priority": 50,
            },
        )
        await client.post(
            "/webhooks/transformations",
            params={"organization_id": str(organization_id)},
            json={
                "endpoint_id": endpoint_id,
                "name": "high-priority",
                "kind": "field_removal",
                "priority": 5,
            },
        )
        resp = await client.get(
            "/webhooks/transformations",
            params={"organization_id": str(organization_id), "endpoint_id": endpoint_id},
        )
        assert resp.status_code == HTTP_OK
        names_in_order = [row["name"] for row in resp.json()["data"]]
        assert names_in_order.index("high-priority") < names_in_order.index("low-priority")

    async def test_list_needs_no_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(
            client, auth_headers, organization_id, "noauth-list-transform-endpoint"
        )
        resp = await client.get(
            "/webhooks/transformations",
            params={"organization_id": str(organization_id), "endpoint_id": endpoint_id},
        )
        assert resp.status_code == HTTP_OK

    async def test_list_returns_404_for_a_missing_endpoint(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/webhooks/transformations",
            params={"organization_id": str(organization_id), "endpoint_id": str(uuid.uuid4())},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestCreateTransformation:
    async def test_create_needs_no_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(
            client, auth_headers, organization_id, "noauth-create-transform-endpoint"
        )
        resp = await client.post(
            "/webhooks/transformations",
            params={"organization_id": str(organization_id)},
            json={"endpoint_id": endpoint_id, "name": "no-auth-rule", "kind": "field_removal"},
        )
        assert resp.status_code == HTTP_CREATED, resp.text

    async def test_create_returns_the_new_rule(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(
            client, auth_headers, organization_id, "create-transform-endpoint"
        )
        resp = await client.post(
            "/webhooks/transformations",
            params={"organization_id": str(organization_id)},
            json={
                "endpoint_id": endpoint_id,
                "name": "add-header",
                "kind": "header_mapping",
                "config": {"add": {"X-Custom": "1"}},
                "priority": 10,
            },
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["name"] == "add-header"
        assert data["kind"] == "header_mapping"
        assert data["config"] == {"add": {"X-Custom": "1"}}
        assert data["priority"] == 10
        assert data["endpoint_id"] == endpoint_id

    async def test_create_returns_404_for_a_missing_endpoint(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/webhooks/transformations",
            params={"organization_id": str(organization_id)},
            json={"endpoint_id": str(uuid.uuid4()), "name": "orphan-rule", "kind": "field_removal"},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestTenantIsolation:
    """Regression tests for a genuine cross-tenant bug.

    ``GET``/``POST /webhooks/transformations`` used to accept any
    ``endpoint_id`` without ever checking it belonged to the caller's own
    ``organization_id`` -- so one organization could list, or attach a
    transformation rule onto, another organization's own endpoint as long
    as it knew (or guessed) the endpoint's id. Both routes now confirm
    ownership via ``EndpointService.get`` first.
    """

    async def test_list_rejects_an_endpoint_from_another_organization(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(
            client, auth_headers, organization_id, "victim-list-endpoint"
        )
        other_org = uuid.uuid4()
        resp = await client.get(
            "/webhooks/transformations",
            params={"organization_id": str(other_org), "endpoint_id": endpoint_id},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_create_rejects_an_endpoint_from_another_organization(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(
            client, auth_headers, organization_id, "victim-create-endpoint"
        )
        other_org = uuid.uuid4()
        resp = await client.post(
            "/webhooks/transformations",
            params={"organization_id": str(other_org)},
            json={"endpoint_id": endpoint_id, "name": "cross-tenant-rule", "kind": "field_removal"},
        )
        assert resp.status_code == HTTP_NOT_FOUND
