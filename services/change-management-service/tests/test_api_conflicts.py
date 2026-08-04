"""HTTP tests for scheduling conflict detection and resolution.

None of these routes take a caller, so no test sends ``Authorization``
headers.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from tests.conftest import HTTP_NOT_FOUND, HTTP_OK

pytestmark = pytest.mark.asyncio


class TestDetectAndList:
    async def test_detect_finds_a_shared_asset_conflict(
        self, client: AsyncClient, organization_id: uuid.UUID, make_scheduled_change
    ) -> None:
        first = await make_scheduled_change(
            title="Patch payments DB", affected_assets=["db-shared-1"]
        )
        second = await make_scheduled_change(
            title="Patch payments cache", affected_assets=["db-shared-1"]
        )

        resp = await client.post(
            f"/changes/{first.id}/conflicts/detect",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        rows = resp.json()["data"]
        assert len(rows) >= 1
        kinds = {row["kind"] for row in rows}
        assert "schedule" in kinds
        assert "asset" in kinds
        assert {row["conflicting_change_id"] for row in rows} == {str(second.id)}

    async def test_detect_returns_404_for_a_missing_change(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/changes/{uuid.uuid4()}/conflicts/detect",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_detect_against_an_unscheduled_change_finds_nothing(
        self, client: AsyncClient, organization_id: uuid.UUID, make_change
    ) -> None:
        created = await make_change()
        resp = await client.post(
            f"/changes/{created.id}/conflicts/detect",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_list_for_change_finds_the_detected_conflicts(
        self, client: AsyncClient, organization_id: uuid.UUID, make_scheduled_change
    ) -> None:
        first = await make_scheduled_change(
            title="Patch payments DB", affected_assets=["db-shared-2"]
        )
        await make_scheduled_change(title="Patch payments cache", affected_assets=["db-shared-2"])
        await client.post(
            f"/changes/{first.id}/conflicts/detect",
            params={"organization_id": str(organization_id)},
        )

        resp = await client.get(
            f"/changes/{first.id}/conflicts", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert len(resp.json()["data"]) >= 1

    async def test_list_active_finds_detected_conflicts(
        self, client: AsyncClient, organization_id: uuid.UUID, make_scheduled_change
    ) -> None:
        first = await make_scheduled_change(
            title="Patch payments DB", affected_assets=["db-shared-3"]
        )
        await make_scheduled_change(title="Patch payments cache", affected_assets=["db-shared-3"])
        detected = await client.post(
            f"/changes/{first.id}/conflicts/detect",
            params={"organization_id": str(organization_id)},
        )
        detected_ids = {row["id"] for row in detected.json()["data"]}

        resp = await client.get("/conflicts", params={"organization_id": str(organization_id)})
        assert resp.status_code == HTTP_OK
        active_ids = {row["id"] for row in resp.json()["data"]}
        assert detected_ids <= active_ids


class TestAcknowledgeAndResolve:
    async def _one_conflict(
        self, client: AsyncClient, organization_id: uuid.UUID, make_scheduled_change
    ) -> dict:
        first = await make_scheduled_change(
            title="Patch payments DB", affected_assets=["db-shared-4"]
        )
        await make_scheduled_change(title="Patch payments cache", affected_assets=["db-shared-4"])
        detected = await client.post(
            f"/changes/{first.id}/conflicts/detect",
            params={"organization_id": str(organization_id)},
        )
        assert detected.status_code == HTTP_OK
        return detected.json()["data"][0]

    async def test_acknowledge_marks_it_acknowledged(
        self, client: AsyncClient, organization_id: uuid.UUID, make_scheduled_change
    ) -> None:
        conflict = await self._one_conflict(client, organization_id, make_scheduled_change)
        resp = await client.post(
            f"/conflicts/{conflict['id']}/acknowledge",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["status"] == "acknowledged"

    async def test_acknowledge_returns_404_for_a_missing_conflict(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/conflicts/{uuid.uuid4()}/acknowledge",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_resolve_records_who_and_why(
        self, client: AsyncClient, organization_id: uuid.UUID, make_scheduled_change
    ) -> None:
        conflict = await self._one_conflict(client, organization_id, make_scheduled_change)
        resp = await client.post(
            f"/conflicts/{conflict['id']}/resolve",
            params={"organization_id": str(organization_id)},
            json={"resolved_by": "ops-lead-1", "note": "Rescheduled the second change."},
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["status"] == "resolved"
        assert data["resolved_by"] == "ops-lead-1"
        assert data["resolution_note"] == "Rescheduled the second change."

    async def test_resolve_returns_404_for_a_missing_conflict(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            f"/conflicts/{uuid.uuid4()}/resolve",
            params={"organization_id": str(organization_id)},
            json={"resolved_by": "ops-lead-1"},
        )
        assert resp.status_code == HTTP_NOT_FOUND
