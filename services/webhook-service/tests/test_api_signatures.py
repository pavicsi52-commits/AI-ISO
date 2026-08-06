"""HTTP tests for /webhooks/signatures.

``POST /webhooks/signatures`` (create) declares no ``caller: CurrentUserId``
parameter and needs no ``Authorization`` header; ``PUT
/webhooks/signatures/rotate`` does and records an audit entry. Both take
``organization_id`` as a query parameter and verify the given
``endpoint_id`` actually belongs to that organization first -- a fix made
in this same change (see the ``TestTenantIsolation`` class below for why).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.enums import AuditAction
from app.repositories.governance import WebhookAuditRepository
from tests.conftest import (
    FAKE_BACKEND_URL,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
)

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


class TestCreateSignature:
    async def test_create_needs_no_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(
            client, auth_headers, organization_id, "noauth-create-sig-endpoint"
        )
        resp = await client.post(
            "/webhooks/signatures",
            params={"organization_id": str(organization_id)},
            json={"endpoint_id": endpoint_id, "secret": "super-secret-value"},
        )
        assert resp.status_code == HTTP_CREATED, resp.text

    async def test_create_returns_the_new_signature(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(
            client, auth_headers, organization_id, "create-sig-endpoint"
        )
        resp = await client.post(
            "/webhooks/signatures",
            params={"organization_id": str(organization_id)},
            json={
                "endpoint_id": endpoint_id,
                "secret": "super-secret-value",
                "algorithm": "hmac_sha512",
            },
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["endpoint_id"] == endpoint_id
        assert data["secret_version"] == 1
        assert data["algorithm"] == "hmac_sha512"
        assert data["status"] == "active"
        # The raw secret is never present anywhere in the response.
        assert "super-secret-value" not in resp.text

    async def test_create_rejects_a_secret_shorter_than_eight_characters(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(
            client, auth_headers, organization_id, "short-secret-endpoint"
        )
        resp = await client.post(
            "/webhooks/signatures",
            params={"organization_id": str(organization_id)},
            json={"endpoint_id": endpoint_id, "secret": "short"},
        )
        assert resp.status_code not in (HTTP_CREATED,)

    async def test_create_returns_404_for_a_missing_endpoint(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/webhooks/signatures",
            params={"organization_id": str(organization_id)},
            json={"endpoint_id": str(uuid.uuid4()), "secret": "super-secret-value"},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestRotateSignature:
    async def test_rotate_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(
            client, auth_headers, organization_id, "noauth-rotate-sig-endpoint"
        )
        await client.post(
            "/webhooks/signatures",
            params={"organization_id": str(organization_id)},
            json={"endpoint_id": endpoint_id, "secret": "original-secret1"},
        )
        resp = await client.put(
            "/webhooks/signatures/rotate",
            params={"organization_id": str(organization_id)},
            json={"endpoint_id": endpoint_id, "new_secret": "rotated-secret12"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_rotate_returns_the_new_active_secret(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(
            client, auth_headers, organization_id, "rotate-sig-endpoint"
        )
        await client.post(
            "/webhooks/signatures",
            params={"organization_id": str(organization_id)},
            json={"endpoint_id": endpoint_id, "secret": "original-secret1"},
        )
        resp = await client.put(
            "/webhooks/signatures/rotate",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "endpoint_id": endpoint_id,
                "new_secret": "rotated-secret12",
                "overlap_hours": 12,
            },
        )
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["secret_version"] == 2
        assert data["status"] == "active"

    async def test_rotate_records_an_audit_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, db_session
    ) -> None:
        endpoint_id = await _create_endpoint(
            client, auth_headers, organization_id, "audit-rotate-sig-endpoint"
        )
        await client.post(
            "/webhooks/signatures",
            params={"organization_id": str(organization_id)},
            json={"endpoint_id": endpoint_id, "secret": "original-secret1"},
        )
        caller = uuid.uuid4()
        resp = await client.put(
            "/webhooks/signatures/rotate",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(caller),
            json={"endpoint_id": endpoint_id, "new_secret": "rotated-secret12"},
        )
        signature_id = resp.json()["data"]["id"]
        entries = await WebhookAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(signature_id)]
        assert len(matching) == 1
        assert matching[0].action == AuditAction.SECRET_ROTATED
        assert matching[0].actor_id == str(caller)

    async def test_rotate_returns_404_for_a_missing_endpoint(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.put(
            "/webhooks/signatures/rotate",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"endpoint_id": str(uuid.uuid4()), "new_secret": "rotated-secret12"},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestTenantIsolation:
    """Regression tests for a genuine cross-tenant bug.

    ``POST``/``PUT .../rotate`` used to accept any ``endpoint_id`` without
    ever checking it belonged to the caller's own ``organization_id`` --
    so one organization could plant, or rotate, a signing secret of its
    own choosing onto another organization's own endpoint, hijacking that
    endpoint's outbound signing. Both routes now confirm ownership via
    ``EndpointService.get`` first.
    """

    async def test_create_rejects_an_endpoint_from_another_organization(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(
            client, auth_headers, organization_id, "victim-create-sig-endpoint"
        )
        other_org = uuid.uuid4()
        resp = await client.post(
            "/webhooks/signatures",
            params={"organization_id": str(other_org)},
            json={"endpoint_id": endpoint_id, "secret": "attacker-secret1"},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_rotate_rejects_an_endpoint_from_another_organization(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(
            client, auth_headers, organization_id, "victim-rotate-sig-endpoint"
        )
        await client.post(
            "/webhooks/signatures",
            params={"organization_id": str(organization_id)},
            json={"endpoint_id": endpoint_id, "secret": "original-secret1"},
        )
        other_org = uuid.uuid4()
        resp = await client.put(
            "/webhooks/signatures/rotate",
            params={"organization_id": str(other_org)},
            headers=auth_headers(uuid.uuid4()),
            json={"endpoint_id": endpoint_id, "new_secret": "attacker-secret12"},
        )
        assert resp.status_code == HTTP_NOT_FOUND
