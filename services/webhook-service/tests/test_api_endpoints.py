"""HTTP tests for /webhooks/endpoints.

``GET`` needs no auth; ``POST``/``PUT``/``DELETE`` declare a
``caller: CurrentUserId`` parameter and need ``Authorization`` headers.
Every route takes ``organization_id`` as a query parameter.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.enums import AuditAction
from app.repositories.governance import WebhookAuditRepository
from tests.conftest import (
    FAKE_BACKEND_URL,
    HTTP_BAD_REQUEST,
    HTTP_CREATED,
    HTTP_NO_CONTENT,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
)

pytestmark = pytest.mark.asyncio


class TestListEndpoints:
    async def test_list_is_empty_before_any_registration(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get("/webhooks/endpoints", params={"organization_id": str(organization_id)})
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_list_finds_a_registered_endpoint(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        await client.post(
            "/webhooks/endpoints",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "orders-endpoint", "url": f"{FAKE_BACKEND_URL}/echo"},
        )
        resp = await client.get("/webhooks/endpoints", params={"organization_id": str(organization_id)})
        assert resp.status_code == HTTP_OK
        names = {row["name"] for row in resp.json()["data"]}
        assert "orders-endpoint" in names

    async def test_list_filters_by_enabled(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/webhooks/endpoints",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"name": "disabled-endpoint", "url": f"{FAKE_BACKEND_URL}/echo"},
        )
        endpoint_id = created.json()["data"]["id"]
        await client.put(
            f"/webhooks/endpoints/{endpoint_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"enabled": False},
        )
        resp = await client.get(
            "/webhooks/endpoints", params={"organization_id": str(organization_id), "enabled": "false"}
        )
        names = {row["name"] for row in resp.json()["data"]}
        assert "disabled-endpoint" in names

        resp_enabled = await client.get(
            "/webhooks/endpoints", params={"organization_id": str(organization_id), "enabled": "true"}
        )
        names_enabled = {row["name"] for row in resp_enabled.json()["data"]}
        assert "disabled-endpoint" not in names_enabled

    async def test_list_tenant_isolation(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        await client.post(
            "/webhooks/endpoints",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "isolated-endpoint", "url": f"{FAKE_BACKEND_URL}/echo"},
        )
        resp = await client.get("/webhooks/endpoints", params={"organization_id": str(uuid.uuid4())})
        assert resp.json()["data"] == []


class TestGetEndpoint:
    async def test_get_finds_a_registered_endpoint(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/webhooks/endpoints",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "get-endpoint", "url": f"{FAKE_BACKEND_URL}/echo"},
        )
        endpoint_id = created.json()["data"]["id"]
        resp = await client.get(
            f"/webhooks/endpoints/{endpoint_id}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == endpoint_id

    async def test_get_returns_404_for_a_missing_endpoint(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/webhooks/endpoints/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_get_is_scoped_to_its_organization(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/webhooks/endpoints",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "scoped-endpoint", "url": f"{FAKE_BACKEND_URL}/echo"},
        )
        endpoint_id = created.json()["data"]["id"]
        resp = await client.get(
            f"/webhooks/endpoints/{endpoint_id}", params={"organization_id": str(uuid.uuid4())}
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestCreateEndpoint:
    async def test_create_requires_auth(self, client: AsyncClient, organization_id: uuid.UUID) -> None:
        resp = await client.post(
            "/webhooks/endpoints",
            params={"organization_id": str(organization_id)},
            json={"name": "no-auth-endpoint", "url": f"{FAKE_BACKEND_URL}/echo"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_create_returns_the_new_endpoint(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/webhooks/endpoints",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "name": "billing-endpoint",
                "url": f"{FAKE_BACKEND_URL}/echo",
                "description": "Billing webhook target.",
                "timeout_seconds": 5.0,
                "max_attempts": 3,
            },
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["name"] == "billing-endpoint"
        assert data["description"] == "Billing webhook target."
        assert data["url"] == f"{FAKE_BACKEND_URL}/echo"
        assert data["timeout_seconds"] == 5.0
        assert data["max_attempts"] == 3
        assert data["status"] == "active"
        assert data["enabled"] is True

    async def test_create_records_an_audit_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, db_session
    ) -> None:
        caller = uuid.uuid4()
        resp = await client.post(
            "/webhooks/endpoints",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(caller),
            json={"name": "audited-endpoint", "url": f"{FAKE_BACKEND_URL}/echo"},
        )
        endpoint_id = resp.json()["data"]["id"]
        entries = await WebhookAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(endpoint_id)]
        assert len(matching) == 1
        assert matching[0].action == AuditAction.ENDPOINT_REGISTERED
        assert matching[0].actor_id == str(caller)

    async def test_create_with_a_missing_name_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/webhooks/endpoints",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"url": f"{FAKE_BACKEND_URL}/echo"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_create_rejects_a_private_address(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/webhooks/endpoints",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "ssrf-endpoint", "url": "http://169.254.169.254/latest/meta-data"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST


class TestUpdateEndpoint:
    async def test_update_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/webhooks/endpoints",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "update-noauth-endpoint", "url": f"{FAKE_BACKEND_URL}/echo"},
        )
        endpoint_id = created.json()["data"]["id"]
        resp = await client.put(
            f"/webhooks/endpoints/{endpoint_id}",
            params={"organization_id": str(organization_id)},
            json={"description": "new description"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_update_edits_fields(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/webhooks/endpoints",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"name": "edit-endpoint", "url": f"{FAKE_BACKEND_URL}/echo"},
        )
        endpoint_id = created.json()["data"]["id"]
        resp = await client.put(
            f"/webhooks/endpoints/{endpoint_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"description": "updated description", "enabled": False},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["description"] == "updated description"
        assert data["enabled"] is False

    async def test_update_revalidates_a_changed_url(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/webhooks/endpoints",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"name": "revalidate-endpoint", "url": f"{FAKE_BACKEND_URL}/echo"},
        )
        endpoint_id = created.json()["data"]["id"]
        resp = await client.put(
            f"/webhooks/endpoints/{endpoint_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"url": "http://10.0.0.5/x"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_update_records_an_audit_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, db_session
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/webhooks/endpoints",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"name": "audit-update-endpoint", "url": f"{FAKE_BACKEND_URL}/echo"},
        )
        endpoint_id = created.json()["data"]["id"]
        await client.put(
            f"/webhooks/endpoints/{endpoint_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"description": "changed"},
        )
        entries = await WebhookAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(endpoint_id)]
        assert AuditAction.ENDPOINT_UPDATED in {e.action for e in matching}

    async def test_update_returns_404_for_a_missing_endpoint(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.put(
            f"/webhooks/endpoints/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"description": "does not matter"},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestDeleteEndpoint:
    async def test_delete_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/webhooks/endpoints",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"name": "delete-noauth-endpoint", "url": f"{FAKE_BACKEND_URL}/echo"},
        )
        endpoint_id = created.json()["data"]["id"]
        resp = await client.delete(
            f"/webhooks/endpoints/{endpoint_id}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_delete_removes_the_endpoint(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/webhooks/endpoints",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"name": "delete-endpoint", "url": f"{FAKE_BACKEND_URL}/echo"},
        )
        endpoint_id = created.json()["data"]["id"]
        resp = await client.delete(
            f"/webhooks/endpoints/{endpoint_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        assert resp.status_code == HTTP_NO_CONTENT

        confirm = await client.get(
            f"/webhooks/endpoints/{endpoint_id}", params={"organization_id": str(organization_id)}
        )
        assert confirm.status_code == HTTP_NOT_FOUND

    async def test_delete_records_an_audit_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, db_session
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/webhooks/endpoints",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"name": "audit-delete-endpoint", "url": f"{FAKE_BACKEND_URL}/echo"},
        )
        endpoint_id = created.json()["data"]["id"]
        await client.delete(
            f"/webhooks/endpoints/{endpoint_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        entries = await WebhookAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(endpoint_id)]
        assert AuditAction.ENDPOINT_DELETED in {e.action for e in matching}

    async def test_delete_returns_404_for_a_missing_endpoint(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.delete(
            f"/webhooks/endpoints/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_NOT_FOUND
