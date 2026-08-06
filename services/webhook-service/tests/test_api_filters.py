"""HTTP tests for /webhooks/filters.

Neither route declares a ``caller: CurrentUserId`` parameter, so neither
needs an ``Authorization`` header. Both take ``organization_id`` as a query
parameter and verify the given ``subscription_id`` actually belongs to that
organization before touching any filter row -- a fix made in this same
change (see the ``TestTenantIsolation`` class below for why).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import FAKE_BACKEND_URL, HTTP_CREATED, HTTP_NOT_FOUND, HTTP_OK

pytestmark = pytest.mark.asyncio


async def _create_subscription(
    client: AsyncClient, auth_headers, organization_id: uuid.UUID, name: str
) -> str:
    endpoint = await client.post(
        "/webhooks/endpoints",
        params={"organization_id": str(organization_id)},
        headers=auth_headers(uuid.uuid4()),
        json={"name": name, "url": f"{FAKE_BACKEND_URL}/echo"},
    )
    endpoint_id = endpoint.json()["data"]["id"]
    subscription = await client.post(
        "/webhooks/subscriptions",
        params={"organization_id": str(organization_id)},
        headers=auth_headers(uuid.uuid4()),
        json={"endpoint_id": endpoint_id, "scope": "wildcard"},
    )
    return subscription.json()["data"]["id"]


class TestListFilters:
    async def test_list_is_empty_before_any_registration(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        subscription_id = await _create_subscription(
            client, auth_headers, organization_id, "list-filter-endpoint"
        )
        resp = await client.get(
            "/webhooks/filters",
            params={"organization_id": str(organization_id), "subscription_id": subscription_id},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_list_finds_a_created_filter(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        subscription_id = await _create_subscription(
            client, auth_headers, organization_id, "find-filter-endpoint"
        )
        await client.post(
            "/webhooks/filters",
            params={"organization_id": str(organization_id)},
            json={"subscription_id": subscription_id, "name": "severity-filter", "rules": []},
        )
        resp = await client.get(
            "/webhooks/filters",
            params={"organization_id": str(organization_id), "subscription_id": subscription_id},
        )
        assert resp.status_code == HTTP_OK
        names = {row["name"] for row in resp.json()["data"]}
        assert "severity-filter" in names

    async def test_list_needs_no_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        subscription_id = await _create_subscription(
            client, auth_headers, organization_id, "noauth-list-filter-endpoint"
        )
        resp = await client.get(
            "/webhooks/filters",
            params={"organization_id": str(organization_id), "subscription_id": subscription_id},
        )
        assert resp.status_code == HTTP_OK

    async def test_list_returns_404_for_a_missing_subscription(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/webhooks/filters",
            params={"organization_id": str(organization_id), "subscription_id": str(uuid.uuid4())},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestCreateFilter:
    async def test_create_needs_no_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        subscription_id = await _create_subscription(
            client, auth_headers, organization_id, "noauth-create-filter-endpoint"
        )
        resp = await client.post(
            "/webhooks/filters",
            params={"organization_id": str(organization_id)},
            json={"subscription_id": subscription_id, "name": "no-auth-filter", "rules": []},
        )
        assert resp.status_code == HTTP_CREATED, resp.text

    async def test_create_returns_the_new_filter(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        subscription_id = await _create_subscription(
            client, auth_headers, organization_id, "create-filter-endpoint"
        )
        rules = [{"field": "severity", "operator": "eq", "value": "critical"}]
        resp = await client.post(
            "/webhooks/filters",
            params={"organization_id": str(organization_id)},
            json={
                "subscription_id": subscription_id,
                "name": "critical-only",
                "match_mode": "any",
                "rules": rules,
            },
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["name"] == "critical-only"
        assert data["match_mode"] == "any"
        assert data["rules"] == rules
        assert data["subscription_id"] == subscription_id

    async def test_create_returns_404_for_a_missing_subscription(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/webhooks/filters",
            params={"organization_id": str(organization_id)},
            json={"subscription_id": str(uuid.uuid4()), "name": "orphan-filter", "rules": []},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestTenantIsolation:
    """Regression tests for a genuine cross-tenant bug.

    ``GET``/``POST /webhooks/filters`` used to accept any
    ``subscription_id`` without ever checking it belonged to the caller's
    own ``organization_id`` -- so one organization could list, or attach a
    filter onto, another organization's own subscription as long as it
    knew (or guessed) the subscription's id. Both routes now confirm
    ownership via ``SubscriptionService.get`` first.
    """

    async def test_list_rejects_a_subscription_from_another_organization(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        subscription_id = await _create_subscription(
            client, auth_headers, organization_id, "victim-list-endpoint"
        )
        other_org = uuid.uuid4()
        resp = await client.get(
            "/webhooks/filters",
            params={"organization_id": str(other_org), "subscription_id": subscription_id},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_create_rejects_a_subscription_from_another_organization(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        subscription_id = await _create_subscription(
            client, auth_headers, organization_id, "victim-create-endpoint"
        )
        other_org = uuid.uuid4()
        resp = await client.post(
            "/webhooks/filters",
            params={"organization_id": str(other_org)},
            json={"subscription_id": subscription_id, "name": "cross-tenant-filter", "rules": []},
        )
        assert resp.status_code == HTTP_NOT_FOUND
