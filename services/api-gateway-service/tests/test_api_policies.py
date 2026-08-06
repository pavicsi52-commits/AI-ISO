"""HTTP tests for /gateway/ratelimits and /gateway/quotas.

Neither router declares a ``caller: CurrentUserId`` parameter, so none of
these routes need ``Authorization`` headers, and none record an audit
entry -- rate-limit/quota policy configuration is not in docs/056's own
"AUDIT" list of administrative changes.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import HTTP_BAD_REQUEST, HTTP_CREATED, HTTP_OK

pytestmark = pytest.mark.asyncio


class TestListRateLimits:
    async def test_list_is_empty_before_any_policy_is_set(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/gateway/ratelimits", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_list_finds_a_configured_policy(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        await client.post(
            "/gateway/ratelimits",
            params={"organization_id": str(organization_id)},
            json={"scope": "organization", "max_requests": 100, "window_seconds": 60},
        )
        resp = await client.get(
            "/gateway/ratelimits", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        scopes = {row["scope"] for row in resp.json()["data"]}
        assert "organization" in scopes


class TestSetRateLimit:
    async def test_set_creates_a_new_policy_with_defaults(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/ratelimits",
            params={"organization_id": str(organization_id)},
            json={"scope": "global", "max_requests": 1000, "window_seconds": 60},
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["scope"] == "global"
        assert data["algorithm"] == "sliding_window"
        assert data["max_requests"] == 1000
        assert data["window_seconds"] == 60
        assert data["burst_max_requests"] is None
        assert data["enabled"] is True

    async def test_set_with_every_field(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/ratelimits",
            params={"organization_id": str(organization_id)},
            json={
                "scope": "api_key",
                "scope_reference": "key-123",
                "algorithm": "token_bucket",
                "max_requests": 50,
                "window_seconds": 30,
                "burst_max_requests": 100,
                "burst_window_seconds": 5,
            },
        )
        assert resp.status_code == HTTP_CREATED
        data = resp.json()["data"]
        assert data["scope"] == "api_key"
        assert data["scope_reference"] == "key-123"
        assert data["algorithm"] == "token_bucket"
        assert data["burst_max_requests"] == 100
        assert data["burst_window_seconds"] == 5

    async def test_set_twice_for_the_same_scope_replaces_rather_than_duplicates(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        first = await client.post(
            "/gateway/ratelimits",
            params={"organization_id": str(organization_id)},
            json={
                "scope": "project",
                "scope_reference": "proj-1",
                "max_requests": 10,
                "window_seconds": 60,
            },
        )
        second = await client.post(
            "/gateway/ratelimits",
            params={"organization_id": str(organization_id)},
            json={
                "scope": "project",
                "scope_reference": "proj-1",
                "max_requests": 20,
                "window_seconds": 120,
            },
        )
        assert second.json()["data"]["id"] == first.json()["data"]["id"]
        assert second.json()["data"]["max_requests"] == 20
        assert second.json()["data"]["window_seconds"] == 120

        listed = await client.get(
            "/gateway/ratelimits", params={"organization_id": str(organization_id)}
        )
        matching = [row for row in listed.json()["data"] if row["scope_reference"] == "proj-1"]
        assert len(matching) == 1

    async def test_set_with_an_invalid_scope_is_a_bad_request(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/ratelimits",
            params={"organization_id": str(organization_id)},
            json={"scope": "not-a-real-scope", "max_requests": 10, "window_seconds": 60},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_set_with_a_zero_max_requests_is_a_bad_request(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/ratelimits",
            params={"organization_id": str(organization_id)},
            json={"scope": "global", "max_requests": 0, "window_seconds": 60},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_set_with_a_window_seconds_over_the_maximum_is_a_bad_request(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/ratelimits",
            params={"organization_id": str(organization_id)},
            json={"scope": "global", "max_requests": 10, "window_seconds": 999_999},
        )
        assert resp.status_code == HTTP_BAD_REQUEST


class TestListQuotas:
    async def test_list_is_empty_before_any_quota_is_set(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get("/gateway/quotas", params={"organization_id": str(organization_id)})
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_list_finds_a_configured_quota(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        await client.post(
            "/gateway/quotas",
            params={"organization_id": str(organization_id)},
            json={
                "scope": "organization",
                "kind": "request",
                "period": "daily",
                "limit_value": 1000,
            },
        )
        resp = await client.get("/gateway/quotas", params={"organization_id": str(organization_id)})
        assert resp.status_code == HTTP_OK
        scopes = {row["scope"] for row in resp.json()["data"]}
        assert "organization" in scopes


class TestSetQuota:
    async def test_set_creates_a_new_quota_with_defaults(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/quotas",
            params={"organization_id": str(organization_id)},
            json={"scope": "global", "limit_value": 500},
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["scope"] == "global"
        assert data["kind"] == "request"
        assert data["period"] == "daily"
        assert data["limit_value"] == 500
        assert data["used_value"] == 0.0
        assert data["enabled"] is True
        assert data["period_started_at"]
        assert data["period_resets_at"]

    async def test_set_with_every_field(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/quotas",
            params={"organization_id": str(organization_id)},
            json={
                "scope": "client",
                "scope_reference": "client-123",
                "kind": "bandwidth",
                "period": "monthly",
                "limit_value": 250.5,
            },
        )
        assert resp.status_code == HTTP_CREATED
        data = resp.json()["data"]
        assert data["scope"] == "client"
        assert data["scope_reference"] == "client-123"
        assert data["kind"] == "bandwidth"
        assert data["period"] == "monthly"
        assert data["limit_value"] == 250.5

    async def test_set_twice_for_the_same_scope_and_kind_replaces_rather_than_duplicates(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        first = await client.post(
            "/gateway/quotas",
            params={"organization_id": str(organization_id)},
            json={
                "scope": "project",
                "scope_reference": "proj-1",
                "kind": "storage",
                "limit_value": 10,
            },
        )
        second = await client.post(
            "/gateway/quotas",
            params={"organization_id": str(organization_id)},
            json={
                "scope": "project",
                "scope_reference": "proj-1",
                "kind": "storage",
                "limit_value": 99,
            },
        )
        assert second.json()["data"]["id"] == first.json()["data"]["id"]
        assert second.json()["data"]["limit_value"] == 99

        listed = await client.get(
            "/gateway/quotas", params={"organization_id": str(organization_id)}
        )
        matching = [row for row in listed.json()["data"] if row["scope_reference"] == "proj-1"]
        assert len(matching) == 1

    async def test_set_with_a_different_kind_for_the_same_scope_creates_a_separate_quota(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        await client.post(
            "/gateway/quotas",
            params={"organization_id": str(organization_id)},
            json={
                "scope": "project",
                "scope_reference": "proj-2",
                "kind": "request",
                "limit_value": 10,
            },
        )
        await client.post(
            "/gateway/quotas",
            params={"organization_id": str(organization_id)},
            json={
                "scope": "project",
                "scope_reference": "proj-2",
                "kind": "bandwidth",
                "limit_value": 20,
            },
        )
        listed = await client.get(
            "/gateway/quotas", params={"organization_id": str(organization_id)}
        )
        matching = [row for row in listed.json()["data"] if row["scope_reference"] == "proj-2"]
        assert len(matching) == 2

    async def test_set_with_an_invalid_kind_is_a_bad_request(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/quotas",
            params={"organization_id": str(organization_id)},
            json={"scope": "global", "kind": "not-a-real-kind", "limit_value": 10},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_set_with_a_zero_limit_value_is_a_bad_request(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/quotas",
            params={"organization_id": str(organization_id)},
            json={"scope": "global", "limit_value": 0},
        )
        assert resp.status_code == HTTP_BAD_REQUEST
