"""HTTP tests for /scheduler/holidays -- holiday calendar entries.

None of these routes declare a ``caller: CurrentUserId`` parameter, so none
of them need ``Authorization`` headers.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from tests.conftest import HTTP_CREATED, HTTP_NOT_FOUND, HTTP_OK

pytestmark = pytest.mark.asyncio


async def _create_holiday(
    client: AsyncClient, organization_id: uuid.UUID, **overrides: object
) -> dict:
    payload = {"name": "New Year's Day", "holiday_date": "2026-01-01", **overrides}
    resp = await client.post(
        "/scheduler/holidays", params={"organization_id": str(organization_id)}, json=payload
    )
    assert resp.status_code == HTTP_CREATED, resp.text
    return resp.json()["data"]


class TestCreateHoliday:
    async def test_create_returns_the_new_recurring_holiday(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        data = await _create_holiday(client, organization_id)
        assert data["name"] == "New Year's Day"
        assert data["holiday_date"] == "2026-01-01"
        assert data["is_recurring"] is True
        assert data["scope"] == "organization"

    async def test_create_a_non_recurring_holiday(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        data = await _create_holiday(
            client,
            organization_id,
            name="Company offsite",
            holiday_date="2026-06-15",
            is_recurring=False,
        )
        assert data["is_recurring"] is False


class TestListHolidays:
    async def test_list_finds_the_created_holiday(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        created = await _create_holiday(client, organization_id)
        resp = await client.get(
            "/scheduler/holidays", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert created["id"] in ids

    async def test_list_filters_a_recurring_holiday_into_any_year(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        created = await _create_holiday(client, organization_id)
        resp = await client.get(
            "/scheduler/holidays", params={"organization_id": str(organization_id), "year": 2030}
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert created["id"] in ids

    async def test_list_filters_out_a_one_off_holiday_from_a_different_year(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        created = await _create_holiday(
            client,
            organization_id,
            name="One-off closure",
            holiday_date="2026-03-10",
            is_recurring=False,
        )
        resp = await client.get(
            "/scheduler/holidays", params={"organization_id": str(organization_id), "year": 2031}
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert created["id"] not in ids


class TestDeleteHoliday:
    async def test_delete_removes_it(self, client: AsyncClient, organization_id: uuid.UUID) -> None:
        created = await _create_holiday(client, organization_id)
        resp = await client.delete(
            f"/scheduler/holidays/{created['id']}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] is None

        listed = await client.get(
            "/scheduler/holidays", params={"organization_id": str(organization_id)}
        )
        assert created["id"] not in {one["id"] for one in listed.json()["data"]}

    async def test_delete_returns_404_for_a_missing_holiday(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.delete(
            f"/scheduler/holidays/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND
