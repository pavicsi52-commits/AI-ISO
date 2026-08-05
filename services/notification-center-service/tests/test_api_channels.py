"""HTTP tests for /notifications/channels.

``GET`` (list) needs no auth; ``PUT`` (configure) declares a
``caller: CurrentUserId`` parameter and needs ``Authorization`` headers.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import HTTP_BAD_REQUEST, HTTP_OK, HTTP_UNAUTHORIZED

pytestmark = pytest.mark.asyncio


class TestList:
    async def test_list_is_empty_before_any_configuration(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/notifications/channels", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_list_finds_a_configured_channel(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        await client.put(
            "/notifications/channels/webhook",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"enabled": True, "config": {"webhook_url": "https://example.test/hook"}},
        )
        resp = await client.get(
            "/notifications/channels", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        channels = {row["channel"] for row in resp.json()["data"]}
        assert "webhook" in channels


class TestSetChannel:
    async def test_set_requires_auth(self, client: AsyncClient, organization_id: uuid.UUID) -> None:
        resp = await client.put(
            "/notifications/channels/webhook",
            params={"organization_id": str(organization_id)},
            json={"enabled": True},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_set_creates_a_new_configuration(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.put(
            "/notifications/channels/slack",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "enabled": True,
                "config": {"webhook_url": "https://hooks.example.test/slack"},
                "description": "Ops alerts channel.",
            },
        )
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["channel"] == "slack"
        assert data["enabled"] is True
        assert data["config"]["webhook_url"] == "https://hooks.example.test/slack"
        assert data["description"] == "Ops alerts channel."

    async def test_set_twice_replaces_the_configuration(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        await client.put(
            "/notifications/channels/teams",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"enabled": True, "config": {"webhook_url": "https://a.test"}},
        )
        resp = await client.put(
            "/notifications/channels/teams",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"enabled": False, "config": {"webhook_url": "https://b.test"}},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["enabled"] is False
        assert data["config"]["webhook_url"] == "https://b.test"

        confirm = await client.get(
            "/notifications/channels", params={"organization_id": str(organization_id)}
        )
        rows = {row["channel"]: row for row in confirm.json()["data"]}
        assert rows["teams"]["enabled"] is False

    async def test_set_with_an_invalid_channel_value_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        # An invalid `NotificationChannelKind` in the path raises a
        # `RequestValidationError` like any other Pydantic-typed
        # parameter -- caught by the same global handler that maps every
        # `RequestValidationError` to `ValidationError` (400), not left
        # as FastAPI's own unmapped 422.
        resp = await client.put(
            "/notifications/channels/not-a-real-channel",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"enabled": True},
        )
        assert resp.status_code == HTTP_BAD_REQUEST
