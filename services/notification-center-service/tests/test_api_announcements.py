"""HTTP tests for /notifications/announcements -- CRUD, publish, broadcast, archive.

``create``/``publish``/``broadcast``/``archive`` all declare a
``caller: CurrentUserId`` parameter; ``update`` does too. Only the two
reads (list, get) need no auth.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from tests.conftest import HTTP_BAD_REQUEST, HTTP_CREATED, HTTP_NOT_FOUND, HTTP_OK, HTTP_UNAUTHORIZED

pytestmark = pytest.mark.asyncio


async def _create_announcement(
    client: AsyncClient, headers: dict[str, str], organization_id: uuid.UUID, **overrides: object
) -> dict:
    payload = {
        "scope": "organization",
        "title": "Scheduled maintenance",
        "body": "We will be down for maintenance tonight.",
        **overrides,
    }
    resp = await client.post(
        "/notifications/announcements",
        params={"organization_id": str(organization_id)},
        headers=headers,
        json=payload,
    )
    assert resp.status_code == HTTP_CREATED, resp.text
    return resp.json()["data"]


class TestCreate:
    async def test_create_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/notifications/announcements",
            params={"organization_id": str(organization_id)},
            json={"scope": "system", "title": "X", "body": "Y"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_create_returns_a_draft(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        data = await _create_announcement(client, auth_headers(uuid.uuid4()), organization_id)
        assert data["status"] == "draft"
        assert data["scope"] == "organization"
        assert data["published_at"] is None
        assert data["is_pinned"] is False

    async def test_create_expires_before_starts_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/notifications/announcements",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={
                "scope": "system",
                "title": "Bad window",
                "body": "Body",
                "starts_at": "2030-01-02T00:00:00Z",
                "expires_at": "2030-01-01T00:00:00Z",
            },
        )
        assert resp.status_code == HTTP_BAD_REQUEST


class TestGetAndList:
    async def test_get_returns_the_announcement(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_announcement(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.get(
            f"/notifications/announcements/{created['id']}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == created["id"]

    async def test_get_returns_404_for_a_missing_announcement(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/notifications/announcements/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_list_finds_the_created_announcement(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_announcement(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.get(
            "/notifications/announcements", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert created["id"] in ids

    async def test_list_filters_by_status(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_announcement(client, auth_headers(uuid.uuid4()), organization_id)
        matching = await client.get(
            "/notifications/announcements",
            params={"organization_id": str(organization_id), "status": "draft"},
        )
        assert created["id"] in {one["id"] for one in matching.json()["data"]}
        non_matching = await client.get(
            "/notifications/announcements",
            params={"organization_id": str(organization_id), "status": "published"},
        )
        assert created["id"] not in {one["id"] for one in non_matching.json()["data"]}


class TestUpdate:
    async def test_update_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_announcement(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.put(
            f"/notifications/announcements/{created['id']}",
            params={"organization_id": str(organization_id)},
            json={"title": "Renamed"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_update_edits_the_title(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_announcement(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.put(
            f"/notifications/announcements/{created['id']}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"title": "Renamed", "is_pinned": True},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["title"] == "Renamed"
        assert data["is_pinned"] is True

    async def test_update_returns_404_for_a_missing_announcement(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.put(
            f"/notifications/announcements/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"title": "Renamed"},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestPublish:
    async def test_publish_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_announcement(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.post(
            f"/notifications/announcements/{created['id']}/publish",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_publish_makes_it_visible(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_announcement(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.post(
            f"/notifications/announcements/{created['id']}/publish",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["status"] == "published"
        assert data["published_at"] is not None

    async def test_publish_twice_is_a_bad_request(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_announcement(client, auth_headers(uuid.uuid4()), organization_id)
        headers = auth_headers(uuid.uuid4())
        await client.post(
            f"/notifications/announcements/{created['id']}/publish",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        resp = await client.post(
            f"/notifications/announcements/{created['id']}/publish",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        assert resp.status_code == HTTP_BAD_REQUEST

    async def test_publish_returns_404_for_a_missing_announcement(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/notifications/announcements/{uuid.uuid4()}/publish",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestBroadcast:
    async def test_broadcast_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_announcement(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.post(
            f"/notifications/announcements/{created['id']}/broadcast",
            params={"organization_id": str(organization_id), "topic": "release-notes"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_broadcast_fans_out_to_the_topics_subscribers(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await _create_announcement(client, headers, organization_id)
        await client.post(
            f"/notifications/announcements/{created['id']}/publish",
            params={"organization_id": str(organization_id)},
            headers=headers,
        )
        await client.post(
            "/notifications/subscriptions",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"user_id": "user-1", "subscription_kind": "topic", "target": "release-notes"},
        )
        resp = await client.post(
            f"/notifications/announcements/{created['id']}/broadcast",
            params={"organization_id": str(organization_id), "topic": "release-notes"},
            headers=headers,
        )
        assert resp.status_code == HTTP_OK, resp.text
        data = resp.json()["data"]
        assert data["announcement_id"] == created["id"]
        assert data["total_recipients"] == 1

    async def test_broadcast_returns_404_for_a_missing_announcement(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/notifications/announcements/{uuid.uuid4()}/broadcast",
            params={"organization_id": str(organization_id), "topic": "release-notes"},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestArchive:
    async def test_archive_requires_auth(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_announcement(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.post(
            f"/notifications/announcements/{created['id']}/archive",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_archive_removes_it_from_the_active_feed(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await _create_announcement(client, auth_headers(uuid.uuid4()), organization_id)
        resp = await client.post(
            f"/notifications/announcements/{created['id']}/archive",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "archived"

    async def test_archive_returns_404_for_a_missing_announcement(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/notifications/announcements/{uuid.uuid4()}/archive",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
        )
        assert resp.status_code == HTTP_NOT_FOUND
