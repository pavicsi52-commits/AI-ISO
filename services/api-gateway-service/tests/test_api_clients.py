"""HTTP tests for /gateway/clients (API client registration).

``GET`` needs no auth; ``POST`` declares a ``caller: CurrentUserId``
parameter and needs ``Authorization`` headers. This router records no
audit entry -- registering a client is a supporting operation for
authentication/API-key-management, not itself part of docs/056's
"AUDIT" list of administrative changes worth an audit trail entry.
"""

from __future__ import annotations

import uuid

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


class TestListClients:
    async def test_list_is_empty_before_any_registration(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/gateway/clients", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_list_finds_a_registered_client(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        await client.post(
            "/gateway/clients",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "mobile-app-client", "client_kind": "mobile_app"},
        )
        resp = await client.get(
            "/gateway/clients", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        names = {row["name"] for row in resp.json()["data"]}
        assert "mobile-app-client" in names

    async def test_list_is_scoped_to_its_organization(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        await client.post(
            "/gateway/clients",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "scoped-client"},
        )
        resp = await client.get("/gateway/clients", params={"organization_id": str(uuid.uuid4())})
        assert resp.json()["data"] == []


class TestGetClient:
    async def test_get_finds_a_registered_client(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/gateway/clients",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "get-client"},
        )
        client_id = created.json()["data"]["id"]
        resp = await client.get(
            f"/gateway/clients/{client_id}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == client_id

    async def test_get_returns_404_for_a_missing_client(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/gateway/clients/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_get_is_scoped_to_its_organization(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/gateway/clients",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "scoped-get-client"},
        )
        client_id = created.json()["data"]["id"]
        resp = await client.get(
            f"/gateway/clients/{client_id}", params={"organization_id": str(uuid.uuid4())}
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestCreateClient:
    async def test_create_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/clients",
            params={"organization_id": str(organization_id)},
            json={"name": "no-auth-client"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_create_returns_the_new_client_with_defaults(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/clients",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "default-client"},
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["name"] == "default-client"
        assert data["client_kind"] == "third_party"
        assert data["enabled"] is True

    async def test_create_with_every_field_set(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/clients",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "name": "full-client",
                "client_kind": "ai_agent",
                "description": "An automated agent integration.",
                "contact_email": "ops@example.test",
            },
        )
        assert resp.status_code == HTTP_CREATED
        data = resp.json()["data"]
        assert data["client_kind"] == "ai_agent"
        assert data["description"] == "An automated agent integration."
        assert data["contact_email"] == "ops@example.test"

    async def test_create_with_a_missing_name_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/clients",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_create_with_an_invalid_client_kind_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/clients",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "bad-kind-client", "client_kind": "not-a-real-kind"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST
