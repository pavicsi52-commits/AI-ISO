"""HTTP tests for /notifications/subscriptions.

Every route here declares a ``caller: CurrentUserId`` parameter and needs
``Authorization`` headers. ``GET`` lists the *calling* user's own
subscriptions (derived from the JWT, not a query parameter); ``POST``
subscribes whichever ``user_id`` the request body names (which may or may
not be the caller -- e.g. an admin subscribing another user); ``DELETE``
unsubscribes whichever ``user_id``/``subscription_kind``/``target`` its
own query parameters name.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import HTTP_CREATED, HTTP_NO_CONTENT, HTTP_NOT_FOUND, HTTP_OK, HTTP_UNAUTHORIZED

pytestmark = pytest.mark.asyncio


class TestList:
    async def test_list_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/notifications/subscriptions", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_list_finds_the_callers_own_subscription(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        caller = uuid.uuid4()
        headers = auth_headers(caller)
        await client.post(
            "/notifications/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"user_id": str(caller), "subscription_kind": "topic", "target": "release-notes"},
        )
        resp = await client.get(
            "/notifications/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        assert resp.status_code == HTTP_OK
        targets = {row["target"] for row in resp.json()["data"]}
        assert "release-notes" in targets

    async def test_list_does_not_return_another_users_subscription(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        other_user = uuid.uuid4()
        await client.post(
            "/notifications/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "user_id": str(other_user),
                "subscription_kind": "topic",
                "target": "release-notes",
            },
        )
        resp = await client.get(
            "/notifications/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []


class TestCreate:
    async def test_create_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/notifications/subscriptions",
            params={"organization_id": str(organization_id)},
            json={"user_id": "user-1", "subscription_kind": "topic", "target": "release-notes"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_create_returns_the_new_subscription(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/notifications/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"user_id": "user-1", "subscription_kind": "topic", "target": "release-notes"},
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["user_id"] == "user-1"
        assert data["subscription_kind"] == "topic"
        assert data["target"] == "release-notes"

    async def test_create_is_idempotent(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        payload = {"user_id": "user-1", "subscription_kind": "event", "target": "job.failed"}
        first = await client.post(
            "/notifications/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json=payload,
        )
        second = await client.post(
            "/notifications/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json=payload,
        )
        assert first.json()["data"]["id"] == second.json()["data"]["id"]

    async def test_create_with_a_webhook_url(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/notifications/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "user_id": "user-1",
                "subscription_kind": "webhook",
                "target": "external-system",
                "webhook_url": "https://example.test/hook",
            },
        )
        assert resp.status_code == HTTP_CREATED
        assert resp.json()["data"]["webhook_url"] == "https://example.test/hook"


class TestDelete:
    async def test_delete_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.delete(
            "/notifications/subscriptions",
            params={
                "organization_id": str(organization_id),
                "user_id": "user-1",
                "subscription_kind": "topic",
                "target": "release-notes",
            },
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_delete_unsubscribes(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        await client.post(
            "/notifications/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"user_id": "user-1", "subscription_kind": "topic", "target": "release-notes"},
        )
        resp = await client.delete(
            "/notifications/subscriptions",
            params={
                "organization_id": str(organization_id),
                "user_id": "user-1",
                "subscription_kind": "topic",
                "target": "release-notes",
            },
            headers=headers,
        )
        assert resp.status_code == HTTP_NO_CONTENT

        confirm = await client.get(
            "/notifications/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        assert confirm.json()["data"] == []

    async def test_delete_returns_404_when_not_subscribed(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.delete(
            "/notifications/subscriptions",
            params={
                "organization_id": str(organization_id),
                "user_id": "user-1",
                "subscription_kind": "topic",
                "target": "never-subscribed",
            },
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_NOT_FOUND
