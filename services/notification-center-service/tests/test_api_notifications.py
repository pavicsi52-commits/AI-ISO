"""HTTP tests for /notifications -- CRUD, lifecycle, send, and broadcast.

Routes whose handler declares a ``caller: CurrentUserId`` parameter
(create, delete, send, broadcast) need ``Authorization`` headers; every
read and every lifecycle transition (read/acknowledge/cancel) does not.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CREATED,
    HTTP_NO_CONTENT,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
)

pytestmark = pytest.mark.asyncio


async def _create_notification(
    client: AsyncClient, headers: dict[str, str], organization_id: uuid.UUID, **overrides: object
) -> dict:
    payload = {
        "user_id": "user-1",
        "body": "Something happened.",
        "source_service": "test-suite",
        **overrides,
    }
    resp = await client.post(
        "/notifications", params={"organization_id": str(organization_id)}, headers=headers, json=payload
    )
    assert resp.status_code == HTTP_CREATED, resp.text
    return resp.json()["data"]


async def _send_notification(
    client: AsyncClient, headers: dict[str, str], organization_id: uuid.UUID, **overrides: object
) -> dict:
    payload = {
        "user_id": "user-1",
        "body": "Something happened.",
        "source_service": "test-suite",
        **overrides,
    }
    resp = await client.post(
        "/notifications/send",
        params={"organization_id": str(organization_id)},
        headers=headers,
        json=payload,
    )
    assert resp.status_code == HTTP_CREATED, resp.text
    return resp.json()["data"]


class TestCreate:
    async def test_create_requires_auth(self, client: AsyncClient, organization_id: uuid.UUID) -> None:
        resp = await client.post(
            "/notifications",
            params={"organization_id": str(organization_id)},
            json={"user_id": "user-1", "body": "Hi", "source_service": "test-suite"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_create_returns_the_new_notification(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        data = await _create_notification(client, auth_headers(uuid.uuid4()), organization_id)
        assert data["user_id"] == "user-1"
        assert data["body"] == "Something happened."
        assert data["status"] == "created"
        assert data["category"] == "information"
        assert data["priority"] == "normal"
        assert data["organization_id"] == str(organization_id)

    async def test_create_with_explicit_category_and_priority(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        data = await _create_notification(
            client,
            auth_headers(uuid.uuid4()),
            organization_id,
            category="alert",
            priority="critical",
            subject="Disk full",
            tags=["ops"],
        )
        assert data["category"] == "alert"
        assert data["priority"] == "critical"
        assert data["subject"] == "Disk full"
        assert data["tags"] == ["ops"]

    async def test_create_missing_required_field_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/notifications",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"user_id": "user-1"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST


class TestGetAndList:
    async def test_get_returns_the_notification(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_notification(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.get(
            f"/notifications/{created['id']}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == created["id"]

    async def test_get_returns_404_for_a_missing_notification(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/notifications/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_list_finds_the_created_notification(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_notification(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.get("/notifications", params={"organization_id": str(organization_id)})
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert created["id"] in ids

    async def test_list_filters_by_status(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_notification(client, auth_headers(uuid.uuid4()), organization_id)
        matching = await client.get(
            "/notifications", params={"organization_id": str(organization_id), "status": "created"}
        )
        assert created["id"] in {one["id"] for one in matching.json()["data"]}
        non_matching = await client.get(
            "/notifications", params={"organization_id": str(organization_id), "status": "read"}
        )
        assert created["id"] not in {one["id"] for one in non_matching.json()["data"]}

    async def test_list_filters_by_category(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_notification(
            client, auth_headers(uuid.uuid4()), organization_id, category="alert"
        )
        matching = await client.get(
            "/notifications", params={"organization_id": str(organization_id), "category": "alert"}
        )
        assert created["id"] in {one["id"] for one in matching.json()["data"]}
        non_matching = await client.get(
            "/notifications", params={"organization_id": str(organization_id), "category": "success"}
        )
        assert created["id"] not in {one["id"] for one in non_matching.json()["data"]}

    async def test_list_filters_by_user_id(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_notification(
            client, auth_headers(uuid.uuid4()), organization_id, user_id="user-42"
        )
        matching = await client.get(
            "/notifications", params={"organization_id": str(organization_id), "user_id": "user-42"}
        )
        assert created["id"] in {one["id"] for one in matching.json()["data"]}
        non_matching = await client.get(
            "/notifications", params={"organization_id": str(organization_id), "user_id": "someone-else"}
        )
        assert created["id"] not in {one["id"] for one in non_matching.json()["data"]}

    async def test_list_filters_by_source_service(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_notification(
            client, auth_headers(uuid.uuid4()), organization_id, source_service="billing-service"
        )
        matching = await client.get(
            "/notifications",
            params={"organization_id": str(organization_id), "source_service": "billing-service"},
        )
        assert created["id"] in {one["id"] for one in matching.json()["data"]}


class TestDelete:
    async def test_delete_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_notification(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.delete(
            f"/notifications/{created['id']}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_delete_soft_deletes_the_notification(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_notification(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.delete(
            f"/notifications/{created['id']}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_NO_CONTENT
        follow_up = await client.get(
            f"/notifications/{created['id']}", params={"organization_id": str(organization_id)}
        )
        assert follow_up.status_code == HTTP_NOT_FOUND

    async def test_delete_returns_404_for_a_missing_notification(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.delete(
            f"/notifications/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestSend:
    async def test_send_requires_auth(self, client: AsyncClient, organization_id: uuid.UUID) -> None:
        resp = await client.post(
            "/notifications/send",
            params={"organization_id": str(organization_id)},
            json={"user_id": "user-1", "body": "Hi", "source_service": "test-suite"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_send_dispatches_and_reports_a_delivered_status(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        # EMAIL is never registered in tests, but IN_APP always is (the
        # real app's own lifespan registers it) -- the aggregate status
        # rolls up to DELIVERED because at least one channel succeeded.
        data = await _send_notification(client, auth_headers(uuid.uuid4()), organization_id)
        assert data["status"] == "delivered"

    async def test_send_with_an_explicit_channel_only_dispatches_that_one(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        data = await _send_notification(
            client, auth_headers(uuid.uuid4()), organization_id, channel="in_app"
        )
        deliveries = await client.get(
            f"/notifications/{data['id']}/deliveries",
            params={"organization_id": str(organization_id)},
        )
        rows = deliveries.json()["data"]
        assert len(rows) == 1
        assert rows[0]["channel"] == "in_app"
        assert rows[0]["status"] == "delivered"

    async def test_send_missing_required_field_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/notifications/send",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"user_id": "user-1"},
        )
        assert resp.status_code == HTTP_BAD_REQUEST


class TestBroadcast:
    async def test_broadcast_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/notifications/broadcast",
            params={"organization_id": str(organization_id)},
            json={"body": "Maintenance tonight.", "recipient_user_ids": ["user-1"]},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_broadcast_to_explicit_recipients_returns_counts(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/notifications/broadcast",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"body": "Maintenance tonight.", "recipient_user_ids": ["user-1", "user-2"]},
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["total_recipients"] == 2
        assert data["status"] == "completed"

    async def test_broadcast_to_a_topics_subscribers(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        await client.post(
            "/notifications/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"user_id": "user-9", "subscription_kind": "topic", "target": "release-notes"},
        )
        resp = await client.post(
            "/notifications/broadcast",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"body": "New release.", "topic": "release-notes"},
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["total_recipients"] == 1
        assert data["topic"] == "release-notes"


class TestLifecycle:
    async def test_mark_read_marks_it_read(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_notification(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.post(
            f"/notifications/{created['id']}/read", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["status"] == "read"
        assert data["read_at"] is not None

    async def test_mark_read_returns_404_for_a_missing_notification(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/notifications/{uuid.uuid4()}/read", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_acknowledge_marks_it_acknowledged(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_notification(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.post(
            f"/notifications/{created['id']}/acknowledge",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["status"] == "acknowledged"
        assert data["acknowledged_at"] is not None
        assert data["read_at"] is not None

    async def test_acknowledge_returns_404_for_a_missing_notification(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/notifications/{uuid.uuid4()}/acknowledge",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_cancel_cancels_an_open_notification(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_notification(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.post(
            f"/notifications/{created['id']}/cancel", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "cancelled"

    async def test_cancel_a_terminal_notification_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_notification(client, auth_headers(uuid.uuid4()), organization_id)
        await client.post(
            f"/notifications/{created['id']}/read", params={"organization_id": str(organization_id)}
        )
        resp = await client.post(
            f"/notifications/{created['id']}/cancel", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_cancel_returns_404_for_a_missing_notification(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/notifications/{uuid.uuid4()}/cancel", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestDeliveries:
    async def test_list_deliveries_after_send(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        data = await _send_notification(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.get(
            f"/notifications/{data['id']}/deliveries",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        rows = resp.json()["data"]
        assert len(rows) >= 1
        assert {row["channel"] for row in rows} <= {"email", "in_app"}

    async def test_list_deliveries_for_a_never_dispatched_notification_is_empty(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_notification(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.get(
            f"/notifications/{created['id']}/deliveries",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_list_deliveries_for_a_missing_notification_is_empty_not_404(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/notifications/{uuid.uuid4()}/deliveries",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []
