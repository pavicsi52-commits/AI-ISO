"""HTTP tests for /gateway/apikeys (API key issue/rotate/revoke).

``GET`` (list) declares no ``caller`` parameter and needs no auth;
``POST``/``PUT .../rotate``/``DELETE`` all declare a
``caller: CurrentUserId`` parameter and need ``Authorization`` headers.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.enums import AuditAction
from app.repositories.governance import ApiAuditRepository
from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
)

pytestmark = pytest.mark.asyncio


class TestListApiKeys:
    async def test_list_is_empty_before_any_key_is_issued(
        self, client: AsyncClient, make_client, organization_id: uuid.UUID
    ) -> None:
        registered_client = await make_client()
        resp = await client.get(
            "/gateway/apikeys",
            params={
                "organization_id": str(organization_id),
                "client_id": str(registered_client.id),
            },
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_list_finds_an_issued_key(
        self, client: AsyncClient, auth_headers, make_client, organization_id: uuid.UUID
    ) -> None:
        registered_client = await make_client()
        await client.post(
            "/gateway/apikeys",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"client_id": str(registered_client.id), "name": "primary-key"},
        )
        resp = await client.get(
            "/gateway/apikeys",
            params={
                "organization_id": str(organization_id),
                "client_id": str(registered_client.id),
            },
        )
        assert resp.status_code == HTTP_OK
        names = {row["name"] for row in resp.json()["data"]}
        assert "primary-key" in names
        # The raw secret is never stored, so the list view must never
        # expose it -- only key_id/name/scopes/status metadata.
        assert "raw_key" not in resp.json()["data"][0]


class TestCreateApiKey:
    async def test_create_requires_auth(
        self, client: AsyncClient, make_client, organization_id: uuid.UUID
    ) -> None:
        registered_client = await make_client()
        resp = await client.post(
            "/gateway/apikeys",
            params={"organization_id": str(organization_id)},
            json={"client_id": str(registered_client.id), "name": "no-auth-key"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_create_returns_the_raw_key_exactly_once(
        self, client: AsyncClient, auth_headers, make_client, organization_id: uuid.UUID
    ) -> None:
        registered_client = await make_client()
        resp = await client.post(
            "/gateway/apikeys",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "client_id": str(registered_client.id),
                "name": "issued-key",
                "scopes": ["gateway:read"],
                "ttl_days": 30,
                "ip_allowlist": ["127.0.0.1"],
            },
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["raw_key"]
        assert data["api_key"]["name"] == "issued-key"
        assert data["api_key"]["scopes"] == ["gateway:read"]
        assert data["api_key"]["ip_allowlist"] == ["127.0.0.1"]
        assert data["api_key"]["status"] == "active"
        assert data["api_key"]["expires_at"] is not None

    async def test_create_records_an_audit_entry_with_api_key_created(
        self, client: AsyncClient, auth_headers, make_client, organization_id: uuid.UUID, db_session
    ) -> None:
        registered_client = await make_client()
        caller = uuid.uuid4()
        resp = await client.post(
            "/gateway/apikeys",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(caller),
            json={"client_id": str(registered_client.id), "name": "audited-key"},
        )
        key_id = resp.json()["data"]["api_key"]["id"]
        entries = await ApiAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(key_id)]
        assert len(matching) == 1
        assert matching[0].action == AuditAction.API_KEY_CREATED
        assert matching[0].actor_id == str(caller)

    async def test_create_with_a_missing_client_id_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/gateway/apikeys",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "missing-client-key"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST


class TestRotateApiKey:
    async def test_rotate_requires_auth(
        self, client: AsyncClient, auth_headers, make_client, organization_id: uuid.UUID
    ) -> None:
        registered_client = await make_client()
        created = await client.post(
            "/gateway/apikeys",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"client_id": str(registered_client.id), "name": "rotate-noauth-key"},
        )
        key_id = created.json()["data"]["api_key"]["id"]
        resp = await client.put(
            f"/gateway/apikeys/{key_id}/rotate", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_rotate_issues_a_new_raw_key(
        self, client: AsyncClient, auth_headers, make_client, organization_id: uuid.UUID
    ) -> None:
        registered_client = await make_client()
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/gateway/apikeys",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"client_id": str(registered_client.id), "name": "rotate-key"},
        )
        original_raw = created.json()["data"]["raw_key"]
        key_id = created.json()["data"]["api_key"]["id"]

        resp = await client.put(
            f"/gateway/apikeys/{key_id}/rotate",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["raw_key"] != original_raw
        assert data["api_key"]["id"] == key_id
        assert data["api_key"]["status"] == "active"

    async def test_rotate_records_an_audit_entry_with_api_key_rotated(
        self, client: AsyncClient, auth_headers, make_client, organization_id: uuid.UUID, db_session
    ) -> None:
        registered_client = await make_client()
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/gateway/apikeys",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"client_id": str(registered_client.id), "name": "audit-rotate-key"},
        )
        key_id = created.json()["data"]["api_key"]["id"]
        await client.put(
            f"/gateway/apikeys/{key_id}/rotate",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        entries = await ApiAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(key_id)]
        assert AuditAction.API_KEY_ROTATED in {e.action for e in matching}

    async def test_rotate_returns_404_for_a_missing_key(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.put(
            f"/gateway/apikeys/{uuid.uuid4()}/rotate",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestRevokeApiKey:
    async def test_revoke_requires_auth(
        self, client: AsyncClient, auth_headers, make_client, organization_id: uuid.UUID
    ) -> None:
        registered_client = await make_client()
        created = await client.post(
            "/gateway/apikeys",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"client_id": str(registered_client.id), "name": "revoke-noauth-key"},
        )
        key_id = created.json()["data"]["api_key"]["id"]
        resp = await client.delete(
            f"/gateway/apikeys/{key_id}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_revoke_marks_the_key_revoked(
        self, client: AsyncClient, auth_headers, make_client, organization_id: uuid.UUID
    ) -> None:
        registered_client = await make_client()
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/gateway/apikeys",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"client_id": str(registered_client.id), "name": "revoke-key"},
        )
        key_id = created.json()["data"]["api_key"]["id"]

        resp = await client.delete(
            f"/gateway/apikeys/{key_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "revoked"

    async def test_revoke_records_an_audit_entry_with_api_key_revoked(
        self, client: AsyncClient, auth_headers, make_client, organization_id: uuid.UUID, db_session
    ) -> None:
        registered_client = await make_client()
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/gateway/apikeys",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"client_id": str(registered_client.id), "name": "audit-revoke-key"},
        )
        key_id = created.json()["data"]["api_key"]["id"]
        await client.delete(
            f"/gateway/apikeys/{key_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        entries = await ApiAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(key_id)]
        assert AuditAction.API_KEY_REVOKED in {e.action for e in matching}

    async def test_revoke_returns_404_for_a_missing_key(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.delete(
            f"/gateway/apikeys/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_NOT_FOUND
