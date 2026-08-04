"""HTTP tests for /notifications/preferences.

Both routes apply to the *calling* user's own preferences only -- the
user id comes from the JWT ``sub`` claim, never from a path or query
parameter -- so both need ``Authorization`` headers.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from tests.conftest import HTTP_OK, HTTP_UNAUTHORIZED

pytestmark = pytest.mark.asyncio


class TestGetPreferences:
    async def test_get_requires_auth(self, client: AsyncClient, organization_id: uuid.UUID) -> None:
        resp = await client.get(
            "/notifications/preferences", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_get_creates_a_permissive_default_on_first_read(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/notifications/preferences",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert set(data["preferred_channels"]) == {"email", "in_app"}
        assert data["muted"] is False
        assert data["digest_frequency"] == "none"

    async def test_get_is_scoped_to_the_calling_user(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        await client.put(
            "/notifications/preferences",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(user_a),
            json={"muted": True},
        )
        resp = await client.get(
            "/notifications/preferences",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(user_b),
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["muted"] is False


class TestUpdatePreferences:
    async def test_update_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.put(
            "/notifications/preferences",
            params={"organization_id": str(organization_id)},
            json={"muted": True},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_update_edits_muted(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        resp = await client.put(
            "/notifications/preferences",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"muted": True},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["muted"] is True

        confirm = await client.get(
            "/notifications/preferences",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        assert confirm.json()["data"]["muted"] is True

    async def test_update_edits_preferred_channels_and_digest_frequency(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        resp = await client.put(
            "/notifications/preferences",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"preferred_channels": ["slack", "email"], "digest_frequency": "daily"},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["preferred_channels"] == ["slack", "email"]
        assert data["digest_frequency"] == "daily"

    async def test_update_edits_quiet_hours_and_timezone(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        resp = await client.put(
            "/notifications/preferences",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={
                "quiet_hours_start": "22:00:00",
                "quiet_hours_end": "06:00:00",
                "timezone": "America/New_York",
                "language": "fr",
            },
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["quiet_hours_start"] == "22:00:00"
        assert data["quiet_hours_end"] == "06:00:00"
        assert data["timezone"] == "America/New_York"
        assert data["language"] == "fr"

    async def test_update_with_no_fields_leaves_defaults_unchanged(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        resp = await client.put(
            "/notifications/preferences",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert set(data["preferred_channels"]) == {"email", "in_app"}
        assert data["muted"] is False
