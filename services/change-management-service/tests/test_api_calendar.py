"""HTTP tests for /calendar -- maintenance windows and blackout periods.

None of these routes need a caller (no ``CurrentUserId`` dependency), so
no test here sends ``Authorization`` headers.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from tests.conftest import HTTP_CREATED, HTTP_NOT_FOUND, HTTP_OK, ago, soon

pytestmark = pytest.mark.asyncio


async def _create_entry(
    client: AsyncClient, organization_id: uuid.UUID, **overrides: object
) -> dict:
    payload = {
        "kind": "maintenance_window",
        "title": "Weekend database patch window",
        "starts_at": soon(1).isoformat(),
        "ends_at": soon(3).isoformat(),
        **overrides,
    }
    resp = await client.post(
        "/calendar", params={"organization_id": str(organization_id)}, json=payload
    )
    assert resp.status_code == HTTP_CREATED, resp.text
    return resp.json()["data"]


class TestCreateAndGet:
    async def test_create_returns_the_new_entry(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        data = await _create_entry(client, organization_id)
        assert data["kind"] == "maintenance_window"
        assert data["title"] == "Weekend database patch window"
        assert data["recurrence"] == "none"
        assert data["is_org_wide"] is True

    async def test_get_returns_the_entry(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        created = await _create_entry(client, organization_id)
        resp = await client.get(
            f"/calendar/{created['id']}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == created["id"]

    async def test_get_returns_404_for_a_missing_entry(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/calendar/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestListInRange:
    async def test_list_finds_an_entry_touching_the_range(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        created = await _create_entry(client, organization_id)
        resp = await client.get(
            "/calendar",
            params={
                "organization_id": str(organization_id),
                "start": soon(0).isoformat(),
                "end": soon(4).isoformat(),
            },
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert created["id"] in ids

    async def test_list_excludes_an_entry_outside_the_range(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        created = await _create_entry(client, organization_id)
        resp = await client.get(
            "/calendar",
            params={
                "organization_id": str(organization_id),
                "start": ago(48).isoformat(),
                "end": ago(24).isoformat(),
            },
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert created["id"] not in ids

    async def test_list_filters_by_kind(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        maintenance = await _create_entry(client, organization_id)
        blackout = await _create_entry(client, organization_id, kind="blackout_period")
        resp = await client.get(
            "/calendar",
            params={
                "organization_id": str(organization_id),
                "start": soon(0).isoformat(),
                "end": soon(4).isoformat(),
                "kind": "blackout_period",
            },
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert blackout["id"] in ids
        assert maintenance["id"] not in ids


class TestAvailability:
    async def test_uncapped_window_is_always_available(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        created = await _create_entry(client, organization_id)
        resp = await client.get(
            f"/calendar/{created['id']}/availability",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["is_available"] is True
        assert data["reason"] is None

    async def test_availability_returns_404_for_a_missing_entry(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/calendar/{uuid.uuid4()}/availability",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_a_full_window_is_reported_unavailable(
        self,
        client: AsyncClient,
        organization_id: uuid.UUID,
        make_approved_change,
        change_service,
    ) -> None:
        entry = await _create_entry(client, organization_id, capacity_limit=1)
        change = await make_approved_change()
        await change_service.schedule(
            organization_id,
            change.id,
            calendar_entry_id=uuid.UUID(entry["id"]),
            scheduled_start_at=soon(1),
            scheduled_end_at=soon(2),
        )

        full = await client.get(
            f"/calendar/{entry['id']}/availability",
            params={"organization_id": str(organization_id)},
        )
        assert full.status_code == HTTP_OK
        assert full.json()["data"]["is_available"] is False

        excluded = await client.get(
            f"/calendar/{entry['id']}/availability",
            params={
                "organization_id": str(organization_id),
                "exclude_change_id": str(change.id),
            },
        )
        assert excluded.status_code == HTTP_OK
        assert excluded.json()["data"]["is_available"] is True
