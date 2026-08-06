"""``/webhooks/replay`` -- the REST surface over `ReplayService`.

Against the real FastAPI app (`app/core/factory.py::create_app`), a real
PostgreSQL-backed session, and a real ASGI backend for any delivery a
replay run actually performs -- see `tests/conftest.py`'s own module
docstring for exactly what the `client`/`app` fixtures override (the
request session and outbound HTTP client only) and what that makes
untestable at this layer (nothing this file needs).

Every management route here takes ``organization_id`` as a query
parameter, confirmed by reading `app/api/replay.py` directly -- none of
them declare a path parameter for it. Only `POST /webhooks/replay` calls
for a caller identity (`CurrentUserId`); every other route in this router
has no such dependency, so it needs no ``Authorization`` header.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.enums import SubscriptionScope
from tests.conftest import (
    FAKE_BACKEND_URL,
    HTTP_BAD_REQUEST,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    AuthHeadersFn,
)

pytestmark = pytest.mark.asyncio


class TestCreateReplayJobApi:
    async def test_create_by_event_succeeds(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, make_event, organization_id
    ) -> None:
        event = await make_event()
        headers = auth_headers(uuid.uuid4())

        response = await client.post(
            "/webhooks/replay",
            params={"organization_id": str(organization_id)},
            json={"scope": "by_event", "event_id": str(event.id)},
            headers=headers,
        )
        assert response.status_code == HTTP_CREATED
        body = response.json()
        assert body["data"]["scope"] == "by_event"
        assert body["data"]["status"] == "pending"

    async def test_create_writes_an_audit_entry(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, make_event, organization_id
    ) -> None:
        event = await make_event()
        headers = auth_headers(uuid.uuid4())

        response = await client.post(
            "/webhooks/replay",
            params={"organization_id": str(organization_id)},
            json={"scope": "by_event", "event_id": str(event.id)},
            headers=headers,
        )
        assert response.status_code == HTTP_CREATED

        audit_response = await client.get(
            "/webhooks/audit", params={"organization_id": str(organization_id)}, headers=headers
        )
        actions = [row["action"] for row in audit_response.json()["data"]]
        assert "replay_started" in actions

    async def test_create_with_missing_required_field_returns_400(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        response = await client.post(
            "/webhooks/replay",
            params={"organization_id": str(organization_id)},
            json={"scope": "by_event"},
            headers=headers,
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_create_by_date_range_with_start_after_end_returns_400(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, organization_id
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        response = await client.post(
            "/webhooks/replay",
            params={"organization_id": str(organization_id)},
            json={
                "scope": "by_date_range",
                "date_range_start": "2026-01-02T00:00:00Z",
                "date_range_end": "2026-01-01T00:00:00Z",
            },
            headers=headers,
        )
        assert response.status_code == HTTP_BAD_REQUEST

    async def test_create_dry_run_is_honoured(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, make_event, organization_id
    ) -> None:
        event = await make_event()
        headers = auth_headers(uuid.uuid4())
        response = await client.post(
            "/webhooks/replay",
            params={"organization_id": str(organization_id)},
            json={"scope": "by_event", "event_id": str(event.id), "dry_run": True},
            headers=headers,
        )
        assert response.status_code == HTTP_CREATED
        assert response.json()["data"]["dry_run"] is True


class TestGetReplayJobApi:
    async def test_get_returns_the_created_job(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, make_event, organization_id
    ) -> None:
        event = await make_event()
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/webhooks/replay",
            params={"organization_id": str(organization_id)},
            json={"scope": "by_event", "event_id": str(event.id)},
            headers=headers,
        )
        job_id = created.json()["data"]["id"]

        response = await client.get(
            f"/webhooks/replay/{job_id}", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["id"] == job_id

    async def test_get_missing_job_returns_404(self, client: AsyncClient, organization_id) -> None:
        response = await client.get(
            f"/webhooks/replay/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_NOT_FOUND

    async def test_get_is_scoped_to_its_organization(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, make_event, organization_id
    ) -> None:
        event = await make_event()
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/webhooks/replay",
            params={"organization_id": str(organization_id)},
            json={"scope": "by_event", "event_id": str(event.id)},
            headers=headers,
        )
        job_id = created.json()["data"]["id"]

        response = await client.get(
            f"/webhooks/replay/{job_id}", params={"organization_id": str(uuid.uuid4())}
        )
        assert response.status_code == HTTP_NOT_FOUND


class TestListReplayJobsApi:
    async def test_list_is_empty_initially(self, client: AsyncClient, organization_id) -> None:
        response = await client.get(
            "/webhooks/replay", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"] == []

    async def test_list_returns_created_jobs(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, make_event, organization_id
    ) -> None:
        event = await make_event()
        headers = auth_headers(uuid.uuid4())
        await client.post(
            "/webhooks/replay",
            params={"organization_id": str(organization_id)},
            json={"scope": "by_event", "event_id": str(event.id)},
            headers=headers,
        )
        response = await client.get(
            "/webhooks/replay", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_OK
        assert len(response.json()["data"]) == 1


class TestPreviewReplayJobApi:
    async def test_preview_reports_the_matching_event(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, make_event, organization_id
    ) -> None:
        event = await make_event()
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/webhooks/replay",
            params={"organization_id": str(organization_id)},
            json={"scope": "by_event", "event_id": str(event.id)},
            headers=headers,
        )
        job_id = created.json()["data"]["id"]

        response = await client.get(
            f"/webhooks/replay/{job_id}/preview", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_OK
        assert response.json()["data"]["matched_count"] == 1
        assert response.json()["data"]["event_ids"] == [str(event.id)]

    async def test_preview_missing_job_returns_404(
        self, client: AsyncClient, organization_id
    ) -> None:
        response = await client.get(
            f"/webhooks/replay/{uuid.uuid4()}/preview",
            params={"organization_id": str(organization_id)},
        )
        assert response.status_code == HTTP_NOT_FOUND


class TestRunReplayJobApi:
    async def test_run_dry_run_job_completes_without_replaying(
        self, client: AsyncClient, auth_headers: AuthHeadersFn, make_event, organization_id
    ) -> None:
        event = await make_event()
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/webhooks/replay",
            params={"organization_id": str(organization_id)},
            json={"scope": "by_event", "event_id": str(event.id), "dry_run": True},
            headers=headers,
        )
        job_id = created.json()["data"]["id"]

        response = await client.post(
            f"/webhooks/replay/{job_id}/run", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_OK
        data = response.json()["data"]
        assert data["status"] == "completed"
        assert data["matched_count"] == 1
        assert data["replayed_count"] == 0
        assert data["failed_count"] == 0

    async def test_run_replays_the_matching_event_for_real(
        self,
        client: AsyncClient,
        auth_headers: AuthHeadersFn,
        make_endpoint,
        make_subscription,
        make_event,
        organization_id,
    ) -> None:
        endpoint = await make_endpoint(url=f"{FAKE_BACKEND_URL}/echo")
        await make_subscription(endpoint.id, scope=SubscriptionScope.WILDCARD)
        event = await make_event()
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/webhooks/replay",
            params={"organization_id": str(organization_id)},
            json={"scope": "by_event", "event_id": str(event.id)},
            headers=headers,
        )
        job_id = created.json()["data"]["id"]

        response = await client.post(
            f"/webhooks/replay/{job_id}/run", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_OK
        data = response.json()["data"]
        assert data["status"] == "completed"
        assert data["replayed_count"] == 1
        assert data["failed_count"] == 0

    async def test_run_missing_job_returns_404(self, client: AsyncClient, organization_id) -> None:
        response = await client.post(
            f"/webhooks/replay/{uuid.uuid4()}/run", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == HTTP_NOT_FOUND
