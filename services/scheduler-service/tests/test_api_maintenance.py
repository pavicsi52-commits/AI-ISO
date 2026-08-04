"""HTTP tests for /scheduler/maintenance -- maintenance windows.

Only ``create_window`` declares ``caller: CurrentUserId``, so only it needs
``Authorization`` headers. ``/active`` is registered before ``/{window_id}``
in the router; a couple of tests here confirm that ordering actually
resolves ``/active`` rather than it being swallowed as a malformed UUID path
param.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
)

pytestmark = pytest.mark.asyncio


async def _create_window(
    client: AsyncClient, headers: dict[str, str], organization_id: uuid.UUID, **overrides: object
) -> dict:
    now = datetime.now(UTC)
    payload = {
        "title": "Nightly database maintenance",
        "starts_at": (now - timedelta(hours=1)).isoformat(),
        "ends_at": (now + timedelta(hours=1)).isoformat(),
        **overrides,
    }
    resp = await client.post(
        "/scheduler/maintenance",
        params={"organization_id": str(organization_id)},
        headers=headers,
        json=payload,
    )
    assert resp.status_code == HTTP_CREATED, resp.text
    return resp.json()["data"]


class TestCreateWindow:
    async def test_create_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        now = datetime.now(UTC)
        resp = await client.post(
            "/scheduler/maintenance",
            params={"organization_id": str(organization_id)},
            json={
                "title": "x",
                "starts_at": now.isoformat(),
                "ends_at": (now + timedelta(hours=1)).isoformat(),
            },
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_create_returns_the_new_window(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        data = await _create_window(client, auth_headers(uuid.uuid4()), organization_id)
        assert data["title"] == "Nightly database maintenance"
        assert data["kind"] == "standard"
        assert data["scope"] == "organization"

    async def test_create_ends_before_it_starts_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        now = datetime.now(UTC)
        resp = await client.post(
            "/scheduler/maintenance",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "title": "Backwards window",
                "starts_at": now.isoformat(),
                "ends_at": (now - timedelta(hours=1)).isoformat(),
            },
        )
        assert resp.status_code == HTTP_BAD_REQUEST


class TestListAndGetWindow:
    async def test_list_finds_the_created_window(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_window(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.get(
            "/scheduler/maintenance", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert created["id"] in ids

    async def test_get_returns_the_window(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_window(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.get(
            f"/scheduler/maintenance/{created['id']}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == created["id"]

    async def test_get_returns_404_for_a_missing_window(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/scheduler/maintenance/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestActiveWindows:
    async def test_active_resolves_ahead_of_the_id_route_and_finds_a_running_window(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_window(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.get(
            "/scheduler/maintenance/active", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert created["id"] in ids

    async def test_active_excludes_a_window_that_has_not_started_yet(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        now = datetime.now(UTC)
        created = await _create_window(
            client,
            auth_headers(uuid.uuid4()),
            organization_id,
            starts_at=(now + timedelta(days=1)).isoformat(),
            ends_at=(now + timedelta(days=2)).isoformat(),
        )
        resp = await client.get(
            "/scheduler/maintenance/active", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert created["id"] not in ids
