"""HTTP tests for /scheduler/priorities -- priority escalation policy.

Neither route declares a ``caller: CurrentUserId`` parameter, so neither
needs ``Authorization`` headers.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from tests.conftest import HTTP_BAD_REQUEST, HTTP_OK

pytestmark = pytest.mark.asyncio


class TestSetPriorityPolicy:
    async def test_set_returns_the_saved_policy(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.put(
            "/scheduler/priorities/critical",
            params={"organization_id": str(organization_id)},
            json={"label": "Critical", "color": "#ff0000", "escalate_after_minutes": 15},
        )
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["priority"] == "critical"
        assert data["label"] == "Critical"
        assert data["color"] == "#ff0000"
        assert data["escalate_after_minutes"] == 15

    async def test_set_twice_replaces_it(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        await client.put(
            "/scheduler/priorities/high",
            params={"organization_id": str(organization_id)},
            json={"label": "High"},
        )
        resp = await client.put(
            "/scheduler/priorities/high",
            params={"organization_id": str(organization_id)},
            json={"label": "High priority (renamed)"},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["label"] == "High priority (renamed)"

    async def test_set_missing_label_is_a_bad_request(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.put(
            "/scheduler/priorities/normal",
            params={"organization_id": str(organization_id)},
            json={},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_set_an_invalid_priority_band_is_a_bad_request(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.put(
            "/scheduler/priorities/urgent",
            params={"organization_id": str(organization_id)},
            json={"label": "Urgent"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST


class TestListPriorityPolicies:
    async def test_list_returns_empty_for_an_org_with_no_policies(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/scheduler/priorities", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_list_finds_the_saved_policy(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        await client.put(
            "/scheduler/priorities/low",
            params={"organization_id": str(organization_id)},
            json={"label": "Low"},
        )
        resp = await client.get(
            "/scheduler/priorities", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        priorities = {one["priority"] for one in resp.json()["data"]}
        assert "low" in priorities
