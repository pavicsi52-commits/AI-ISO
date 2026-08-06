"""HTTP tests for /webhooks/subscriptions.

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
    HTTP_CREATED,
    HTTP_NO_CONTENT,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
)

pytestmark = pytest.mark.asyncio


async def _create_endpoint(client: AsyncClient, auth_headers, organization_id: uuid.UUID, name: str) -> str:
    resp = await client.post(
        "/webhooks/endpoints",
        params={"organization_id": str(organization_id)},
        headers=auth_headers(uuid.uuid4()),
        json={"name": name, "url": f"{FAKE_BACKEND_URL}/echo"},
    )
    return resp.json()["data"]["id"]


class TestListSubscriptions:
    async def test_list_is_empty_before_any_registration(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/webhooks/subscriptions", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_list_finds_a_registered_subscription(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(client, auth_headers, organization_id, "sub-endpoint")
        await client.post(
            "/webhooks/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"endpoint_id": endpoint_id, "scope": "wildcard"},
        )
        resp = await client.get(
            "/webhooks/subscriptions", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        endpoint_ids = {row["endpoint_id"] for row in resp.json()["data"]}
        assert endpoint_id in endpoint_ids

    async def test_list_tenant_isolation(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(client, auth_headers, organization_id, "isolated-sub-endpoint")
        await client.post(
            "/webhooks/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"endpoint_id": endpoint_id, "scope": "wildcard"},
        )
        resp = await client.get("/webhooks/subscriptions", params={"organization_id": str(uuid.uuid4())})
        assert resp.json()["data"] == []


class TestGetSubscription:
    async def test_get_finds_a_registered_subscription(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(client, auth_headers, organization_id, "get-sub-endpoint")
        created = await client.post(
            "/webhooks/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"endpoint_id": endpoint_id, "scope": "wildcard"},
        )
        subscription_id = created.json()["data"]["id"]
        resp = await client.get(
            f"/webhooks/subscriptions/{subscription_id}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == subscription_id

    async def test_get_returns_404_for_a_missing_subscription(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/webhooks/subscriptions/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_get_is_scoped_to_its_organization(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(client, auth_headers, organization_id, "scoped-sub-endpoint")
        created = await client.post(
            "/webhooks/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"endpoint_id": endpoint_id, "scope": "wildcard"},
        )
        subscription_id = created.json()["data"]["id"]
        resp = await client.get(
            f"/webhooks/subscriptions/{subscription_id}", params={"organization_id": str(uuid.uuid4())}
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestCreateSubscription:
    async def test_create_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(client, auth_headers, organization_id, "noauth-sub-endpoint")
        resp = await client.post(
            "/webhooks/subscriptions",
            params={"organization_id": str(organization_id)},
            json={"endpoint_id": endpoint_id, "scope": "wildcard"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_create_returns_the_new_subscription(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(client, auth_headers, organization_id, "create-sub-endpoint")
        resp = await client.post(
            "/webhooks/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "endpoint_id": endpoint_id,
                "scope": "event",
                "scope_reference": "order.*",
                "event_types": ["order.created"],
            },
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["endpoint_id"] == endpoint_id
        assert data["scope"] == "event"
        assert data["scope_reference"] == "order.*"
        assert data["event_types"] == ["order.created"]
        assert data["enabled"] is True

    async def test_create_records_an_audit_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, db_session
    ) -> None:
        endpoint_id = await _create_endpoint(client, auth_headers, organization_id, "audit-sub-endpoint")
        caller = uuid.uuid4()
        resp = await client.post(
            "/webhooks/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(caller),
            json={"endpoint_id": endpoint_id, "scope": "wildcard"},
        )
        subscription_id = resp.json()["data"]["id"]
        entries = await WebhookAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(subscription_id)]
        assert len(matching) == 1
        assert matching[0].action == AuditAction.SUBSCRIPTION_CREATED
        assert matching[0].actor_id == str(caller)


class TestUpdateSubscription:
    async def test_update_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(client, auth_headers, organization_id, "update-noauth-sub-endpoint")
        created = await client.post(
            "/webhooks/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"endpoint_id": endpoint_id, "scope": "wildcard"},
        )
        subscription_id = created.json()["data"]["id"]
        resp = await client.put(
            f"/webhooks/subscriptions/{subscription_id}",
            params={"organization_id": str(organization_id)},
            json={"enabled": False},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_update_edits_fields(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        endpoint_id = await _create_endpoint(client, auth_headers, organization_id, "edit-sub-endpoint")
        created = await client.post(
            "/webhooks/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"endpoint_id": endpoint_id, "scope": "wildcard"},
        )
        subscription_id = created.json()["data"]["id"]
        resp = await client.put(
            f"/webhooks/subscriptions/{subscription_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"event_types": ["order.created"], "enabled": False},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["event_types"] == ["order.created"]
        assert data["enabled"] is False

    async def test_update_records_an_audit_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, db_session
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        endpoint_id = await _create_endpoint(client, auth_headers, organization_id, "audit-update-sub-endpoint")
        created = await client.post(
            "/webhooks/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"endpoint_id": endpoint_id, "scope": "wildcard"},
        )
        subscription_id = created.json()["data"]["id"]
        await client.put(
            f"/webhooks/subscriptions/{subscription_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"enabled": False},
        )
        entries = await WebhookAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(subscription_id)]
        assert AuditAction.SUBSCRIPTION_UPDATED in {e.action for e in matching}

    async def test_update_returns_404_for_a_missing_subscription(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.put(
            f"/webhooks/subscriptions/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"enabled": False},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestDeleteSubscription:
    async def test_delete_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        endpoint_id = await _create_endpoint(client, auth_headers, organization_id, "delete-noauth-sub-endpoint")
        created = await client.post(
            "/webhooks/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"endpoint_id": endpoint_id, "scope": "wildcard"},
        )
        subscription_id = created.json()["data"]["id"]
        resp = await client.delete(
            f"/webhooks/subscriptions/{subscription_id}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_delete_removes_the_subscription(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        endpoint_id = await _create_endpoint(client, auth_headers, organization_id, "delete-sub-endpoint")
        created = await client.post(
            "/webhooks/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"endpoint_id": endpoint_id, "scope": "wildcard"},
        )
        subscription_id = created.json()["data"]["id"]
        resp = await client.delete(
            f"/webhooks/subscriptions/{subscription_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        assert resp.status_code == HTTP_NO_CONTENT

        confirm = await client.get(
            f"/webhooks/subscriptions/{subscription_id}", params={"organization_id": str(organization_id)}
        )
        assert confirm.status_code == HTTP_NOT_FOUND

    async def test_delete_records_an_audit_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, db_session
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        endpoint_id = await _create_endpoint(client, auth_headers, organization_id, "audit-delete-sub-endpoint")
        created = await client.post(
            "/webhooks/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"endpoint_id": endpoint_id, "scope": "wildcard"},
        )
        subscription_id = created.json()["data"]["id"]
        await client.delete(
            f"/webhooks/subscriptions/{subscription_id}",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        entries = await WebhookAuditRepository(db_session).list_for_org(organization_id)
        matching = [e for e in entries if e.entity_id == uuid.UUID(subscription_id)]
        assert AuditAction.SUBSCRIPTION_DELETED in {e.action for e in matching}

    async def test_delete_returns_404_for_a_missing_subscription(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.delete(
            f"/webhooks/subscriptions/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_NOT_FOUND
