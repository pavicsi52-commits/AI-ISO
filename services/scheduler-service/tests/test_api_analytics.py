"""HTTP tests for analytics -- /scheduler/statistics, /scheduler/reports, /scheduler/audit.

Only ``generate_report`` declares ``audit: AuditSvc`` and
``caller: CurrentUserId``, so only it needs ``Authorization`` headers.
Every other route here (dashboard, rollup, trend, list/get/download report,
audit list/summary) does not.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from tests.conftest import HTTP_CREATED, HTTP_NOT_FOUND, HTTP_OK, HTTP_UNAUTHORIZED

from app.models.enums import ReportFormat, ReportKind, ReportStatus
from app.models.governance import SchedulerReport

pytestmark = pytest.mark.asyncio


class TestDashboard:
    async def test_dashboard_returns_a_snapshot(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job
    ) -> None:
        await make_job()
        resp = await client.get(
            "/scheduler/statistics/dashboard", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert "jobs_by_status" in data
        assert "queue_length" in data
        assert "latest_window" in data


class TestRollupAndTrend:
    async def test_rollup_creates_a_statistics_window(
        self, client: AsyncClient, organization_id: uuid.UUID, make_job, execution_service
    ) -> None:
        job = await make_job()
        await execution_service.dispatch(organization_id, job.id, trigger_source="manual")
        now = datetime.now(UTC)
        resp = await client.post(
            "/scheduler/statistics",
            params={"organization_id": str(organization_id)},
            json={
                "window_start": (now - timedelta(hours=1)).isoformat(),
                "window_end": (now + timedelta(hours=1)).isoformat(),
            },
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["jobs_scheduled"] >= 1
        assert data["jobs_completed"] >= 1

    async def test_trend_returns_the_rolled_up_window(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        now = datetime.now(UTC)
        created = await client.post(
            "/scheduler/statistics",
            params={"organization_id": str(organization_id)},
            json={
                "window_start": (now - timedelta(hours=1)).isoformat(),
                "window_end": (now + timedelta(hours=1)).isoformat(),
            },
        )
        window_id = created.json()["data"]["id"]
        resp = await client.get(
            "/scheduler/statistics",
            params={"organization_id": str(organization_id), "since_days": 7},
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert window_id in ids


class TestReports:
    async def test_generate_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/scheduler/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "execution"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_generate_returns_a_completed_report(
        self,
        client: AsyncClient,
        auth_headers,
        organization_id: uuid.UUID,
        make_job,
        execution_service,
    ) -> None:
        job = await make_job()
        await execution_service.dispatch(organization_id, job.id, trigger_source="manual")
        resp = await client.post(
            "/scheduler/reports",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"kind": "execution", "report_format": "json"},
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["status"] == "completed"
        assert data["kind"] == "execution"
        assert data["row_count"] >= 1

    async def test_list_finds_the_generated_report(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/scheduler/reports",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"kind": "failure", "report_format": "json"},
        )
        report_id = created.json()["data"]["id"]
        resp = await client.get(
            "/scheduler/reports", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert report_id in ids

    async def test_get_returns_the_report(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        created = await client.post(
            "/scheduler/reports",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"kind": "performance", "report_format": "json"},
        )
        report_id = created.json()["data"]["id"]
        resp = await client.get(
            f"/scheduler/reports/{report_id}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == report_id

    async def test_get_returns_404_for_a_missing_report(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/scheduler/reports/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestDownloadReport:
    async def _generate(
        self,
        client: AsyncClient,
        headers: dict[str, str],
        organization_id: uuid.UUID,
        *,
        report_format: str,
    ) -> str:
        created = await client.post(
            "/scheduler/reports",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"kind": "execution", "report_format": report_format},
        )
        assert created.status_code == HTTP_CREATED, created.text
        return created.json()["data"]["id"]

    async def test_download_json_returns_the_success_envelope(
        self,
        client: AsyncClient,
        auth_headers,
        organization_id: uuid.UUID,
        make_job,
        execution_service,
    ) -> None:
        job = await make_job()
        await execution_service.dispatch(organization_id, job.id, trigger_source="manual")
        headers = auth_headers(uuid.uuid4())
        report_id = await self._generate(client, headers, organization_id, report_format="json")
        resp = await client.get(
            f"/scheduler/reports/{report_id}/download",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert "application/json" in resp.headers["content-type"]
        rows = resp.json()["data"]["rows"]
        assert len(rows) >= 1

    async def test_download_csv_returns_plain_text(
        self,
        client: AsyncClient,
        auth_headers,
        organization_id: uuid.UUID,
        make_job,
        execution_service,
    ) -> None:
        job = await make_job()
        await execution_service.dispatch(organization_id, job.id, trigger_source="manual")
        headers = auth_headers(uuid.uuid4())
        report_id = await self._generate(client, headers, organization_id, report_format="csv")
        resp = await client.get(
            f"/scheduler/reports/{report_id}/download",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.headers["content-type"].startswith("text/csv")
        assert "job_id" in resp.text

    async def test_download_markdown_returns_plain_text(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        report_id = await self._generate(client, headers, organization_id, report_format="markdown")
        resp = await client.get(
            f"/scheduler/reports/{report_id}/download",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.headers["content-type"].startswith("text/markdown")
        assert resp.text.startswith("# ")

    async def test_download_returns_404_when_the_report_is_not_completed(
        self, client: AsyncClient, organization_id: uuid.UUID, reports_repo
    ) -> None:
        pending = await reports_repo.create(
            SchedulerReport(
                organization_id=organization_id,
                kind=ReportKind.EXECUTION,
                report_format=ReportFormat.JSON,
                title="Still running",
                status=ReportStatus.PENDING,
            )
        )
        resp = await client.get(
            f"/scheduler/reports/{pending.id}/download",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestAudit:
    async def test_list_finds_a_recorded_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        await client.post(
            "/scheduler/reports",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"kind": "execution", "report_format": "json"},
        )
        resp = await client.get(
            "/scheduler/audit", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        actions = {one["action"] for one in resp.json()["data"]}
        assert "report_generated" in actions

    async def test_list_filters_by_action(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        await client.post(
            "/scheduler/reports",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"kind": "execution", "report_format": "json"},
        )
        matching = await client.get(
            "/scheduler/audit",
            params={"organization_id": str(organization_id), "action": "report_generated"},
        )
        assert matching.status_code == HTTP_OK
        assert len(matching.json()["data"]) >= 1
        non_matching = await client.get(
            "/scheduler/audit",
            params={"organization_id": str(organization_id), "action": "job_paused"},
        )
        assert non_matching.json()["data"] == []

    async def test_summary_counts_recorded_actions(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        headers = auth_headers(uuid.uuid4())
        await client.post(
            "/scheduler/reports",
            params={"organization_id": str(organization_id)},
            headers=headers,
            json={"kind": "execution", "report_format": "json"},
        )
        resp = await client.get(
            "/scheduler/audit/summary", params={"organization_id": str(organization_id), "days": 7}
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["total"] >= 1
        assert data["by_action"].get("report_generated", 0) >= 1
