"""HTTP tests for statistics, generated reports, and the audit trail.

Only ``generate_report`` declares a ``caller: CurrentUserId`` parameter
and needs ``Authorization`` headers; every other route here does not.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from tests.conftest import (
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_UNAUTHORIZED,
    ago,
    soon,
)

pytestmark = pytest.mark.asyncio


class TestStatistics:
    async def test_dashboard_returns_a_snapshot(
        self, client: AsyncClient, organization_id: uuid.UUID, make_change
    ) -> None:
        await make_change()
        resp = await client.get(
            "/statistics/dashboard", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert "by_status" in data
        assert "active_conflicts" in data
        assert "latest_window" in data

    async def test_rollup_computes_a_window(
        self, client: AsyncClient, organization_id: uuid.UUID, make_change
    ) -> None:
        await make_change()
        resp = await client.post(
            "/statistics/rollup",
            params={"organization_id": str(organization_id)},
            json={"window_start": ago(1).isoformat(), "window_end": soon(1).isoformat()},
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["changes_created"] >= 1
        assert "by_category" in data

    async def test_rollup_is_idempotent_by_window_start(
        self, client: AsyncClient, organization_id: uuid.UUID, make_change
    ) -> None:
        window_start = ago(1)
        window_end = soon(1)
        await make_change()
        first = await client.post(
            "/statistics/rollup",
            params={"organization_id": str(organization_id)},
            json={"window_start": window_start.isoformat(), "window_end": window_end.isoformat()},
        )
        await make_change()
        second = await client.post(
            "/statistics/rollup",
            params={"organization_id": str(organization_id)},
            json={"window_start": window_start.isoformat(), "window_end": window_end.isoformat()},
        )
        assert first.json()["data"]["id"] == second.json()["data"]["id"]
        assert second.json()["data"]["changes_created"] == 2

    async def test_trend_finds_a_rolled_up_window(
        self, client: AsyncClient, organization_id: uuid.UUID, make_change
    ) -> None:
        await make_change()
        await client.post(
            "/statistics/rollup",
            params={"organization_id": str(organization_id)},
            json={"window_start": ago(1).isoformat(), "window_end": soon(1).isoformat()},
        )
        resp = await client.get(
            "/statistics/trend",
            params={"organization_id": str(organization_id), "since_days": 7},
        )
        assert resp.status_code == HTTP_OK
        assert len(resp.json()["data"]) >= 1


class TestReports:
    async def test_generate_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "change"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_generate_a_change_report(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_change
    ) -> None:
        await make_change()
        resp = await client.post(
            "/reports",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"kind": "change", "report_format": "json", "title": "Weekly change report"},
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["kind"] == "change"
        assert data["status"] == "completed"
        assert data["row_count"] >= 1

    async def test_generate_an_executive_report(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/reports",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"kind": "executive", "report_format": "csv"},
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        assert resp.json()["data"]["status"] == "completed"

    async def test_generate_a_risk_report(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_assessed_change
    ) -> None:
        await make_assessed_change()
        resp = await client.post(
            "/reports",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"kind": "risk", "report_format": "markdown"},
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["kind"] == "risk"
        assert data["row_count"] >= 1

    async def test_list_finds_generated_reports(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/reports",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"kind": "change"},
        )
        resp = await client.get("/reports", params={"organization_id": str(organization_id)})
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert created.json()["data"]["id"] in ids

    async def test_get_returns_the_report(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/reports",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"kind": "change"},
        )
        report_id = created.json()["data"]["id"]
        resp = await client.get(
            f"/reports/{report_id}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == report_id

    async def test_get_returns_404_for_a_missing_report(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/reports/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestDownload:
    async def _generate(
        self,
        client: AsyncClient,
        auth_headers,
        organization_id: uuid.UUID,
        report_format: str,
    ) -> str:
        created = await client.post(
            "/reports",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"kind": "change", "report_format": report_format},
        )
        assert created.status_code == HTTP_CREATED
        return created.json()["data"]["id"]

    async def test_download_as_csv(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_change
    ) -> None:
        await make_change()
        report_id = await self._generate(client, auth_headers, organization_id, "csv")
        resp = await client.get(
            f"/reports/{report_id}/download", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK, resp.text
        assert "text/csv" in resp.headers["content-type"]
        assert "reference" in resp.text

    async def test_download_as_markdown(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_change
    ) -> None:
        await make_change()
        report_id = await self._generate(client, auth_headers, organization_id, "markdown")
        resp = await client.get(
            f"/reports/{report_id}/download", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK, resp.text
        assert "text/markdown" in resp.headers["content-type"]
        assert resp.text.startswith("# ")

    async def test_download_as_json(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID, make_change
    ) -> None:
        await make_change()
        report_id = await self._generate(client, auth_headers, organization_id, "json")
        resp = await client.get(
            f"/reports/{report_id}/download", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK, resp.text
        assert "application/json" in resp.headers["content-type"]
        data = resp.json()["data"]
        assert "rows" in data
        assert isinstance(data["rows"], list)

    async def test_download_returns_404_for_a_missing_report(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/reports/{uuid.uuid4()}/download", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestAudit:
    async def test_list_finds_recorded_entries(
        self, client: AsyncClient, organization_id: uuid.UUID, audit_service
    ) -> None:
        await audit_service.record(
            organization_id,
            action="change_created",
            entity_type="change",
            summary="Opened CHG-0001.",
            actor_id="requester-1",
        )
        await audit_service.record(
            organization_id,
            action="change_submitted",
            entity_type="change",
            summary="Submitted CHG-0001.",
            actor_id="requester-1",
        )
        resp = await client.get("/audit", params={"organization_id": str(organization_id)})
        assert resp.status_code == HTTP_OK
        assert len(resp.json()["data"]) == 2

    async def test_list_filters_by_action(
        self, client: AsyncClient, organization_id: uuid.UUID, audit_service
    ) -> None:
        await audit_service.record(
            organization_id,
            action="change_created",
            entity_type="change",
            summary="Opened CHG-0002.",
        )
        await audit_service.record(
            organization_id,
            action="change_submitted",
            entity_type="change",
            summary="Submitted CHG-0002.",
        )
        resp = await client.get(
            "/audit",
            params={"organization_id": str(organization_id), "action": "change_submitted"},
        )
        assert resp.status_code == HTTP_OK
        rows = resp.json()["data"]
        assert len(rows) == 1
        assert rows[0]["action"] == "change_submitted"

    async def test_summary_counts_by_action(
        self, client: AsyncClient, organization_id: uuid.UUID, audit_service
    ) -> None:
        await audit_service.record(
            organization_id,
            action="change_created",
            entity_type="change",
            summary="Opened CHG-0003.",
        )
        resp = await client.get(
            "/audit/summary", params={"organization_id": str(organization_id), "days": 7}
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["total"] >= 1
        assert data["by_action"]["change_created"] >= 1
