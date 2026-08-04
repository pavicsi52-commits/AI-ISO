"""HTTP tests for /notifications/statistics, /reports, and /audit.

Only ``POST /reports`` declares a ``caller: CurrentUserId`` parameter and
needs ``Authorization`` headers; every other route here (statistics,
trend, list/get/download reports, audit list/summary) does not.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.conftest import HTTP_CREATED, HTTP_NOT_FOUND, HTTP_OK, HTTP_UNAUTHORIZED

from app.models.enums import ReportFormat, ReportKind, ReportStatus
from app.models.governance import NotificationReport
from app.repositories.governance import NotificationReportRepository

pytestmark = pytest.mark.asyncio


class TestStatistics:
    async def test_statistics_returns_a_dashboard_snapshot(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/notifications/statistics", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert "deliveries_by_status" in data
        assert "queue_length" in data
        assert "latest_window" in data

    async def test_statistics_reflects_a_dispatched_notification(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        await client.post(
            "/notifications/send",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"user_id": "user-1", "body": "Hi", "source_service": "test-suite", "channel": "in_app"},
        )
        resp = await client.get(
            "/notifications/statistics", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        by_status = resp.json()["data"]["deliveries_by_status"]
        assert by_status.get("delivered", 0) >= 1


class TestStatisticsTrend:
    async def test_trend_is_empty_with_no_rollups_yet(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/notifications/statistics/trend", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"] == []

    async def test_trend_accepts_since_days(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/notifications/statistics/trend",
            params={"organization_id": str(organization_id), "since_days": 7},
        )
        assert resp.status_code == HTTP_OK


class TestReports:
    async def test_generate_requires_auth(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/notifications/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "delivery"},
        )
        assert resp.status_code == HTTP_UNAUTHORIZED

    async def test_generate_a_json_delivery_report(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        resp = await client.post(
            "/notifications/reports",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"kind": "delivery", "report_format": "json", "title": "Delivery report"},
        )
        assert resp.status_code == HTTP_CREATED, resp.text
        data = resp.json()["data"]
        assert data["kind"] == "delivery"
        assert data["status"] == "completed"
        assert data["title"] == "Delivery report"
        assert "rows" in data["content"]

    async def test_get_returns_the_report(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/notifications/reports",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"kind": "audit"},
        )
        report_id = created.json()["data"]["id"]
        resp = await client.get(
            f"/notifications/reports/{report_id}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        assert resp.json()["data"]["id"] == report_id

    async def test_get_returns_404_for_a_missing_report(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/notifications/reports/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_list_finds_the_generated_report(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/notifications/reports",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"kind": "failure"},
        )
        report_id = created.json()["data"]["id"]
        resp = await client.get(
            "/notifications/reports", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        ids = {one["id"] for one in resp.json()["data"]}
        assert report_id in ids


class TestReportDownload:
    async def test_download_a_json_report_returns_the_envelope(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/notifications/reports",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"kind": "audit", "report_format": "json"},
        )
        report_id = created.json()["data"]["id"]
        resp = await client.get(
            f"/notifications/reports/{report_id}/download",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        body = resp.json()
        assert body["success"] is True
        assert "rows" in body["data"]

    async def test_download_a_csv_report_returns_plain_text(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/notifications/reports",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"kind": "delivery", "report_format": "csv"},
        )
        report_id = created.json()["data"]["id"]
        resp = await client.get(
            f"/notifications/reports/{report_id}/download",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.headers["content-type"].startswith("text/csv")

    async def test_download_a_markdown_report_returns_plain_text(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        created = await client.post(
            "/notifications/reports",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"kind": "retry", "report_format": "markdown", "title": "Retry report"},
        )
        report_id = created.json()["data"]["id"]
        resp = await client.get(
            f"/notifications/reports/{report_id}/download",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_OK
        assert resp.headers["content-type"].startswith("text/markdown")
        assert resp.text.startswith("# Retry report")

    async def test_download_returns_404_for_a_missing_report(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            f"/notifications/reports/{uuid.uuid4()}/download",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND

    async def test_download_a_report_still_generating_is_404(
        self, client: AsyncClient, db_session: AsyncSession, organization_id: uuid.UUID
    ) -> None:
        # `ReportService.generate` always resolves synchronously to
        # COMPLETED or FAILED over HTTP -- reaching a PENDING/RUNNING row
        # means seeding one directly, the same way a real deferred report
        # build would leave one mid-flight.
        report = await NotificationReportRepository(db_session).create(
            NotificationReport(
                organization_id=organization_id,
                kind=ReportKind.DELIVERY,
                report_format=ReportFormat.JSON,
                title="Still generating",
                status=ReportStatus.RUNNING,
                generated_by=None,
            )
        )
        resp = await client.get(
            f"/notifications/reports/{report.id}/download",
            params={"organization_id": str(organization_id)},
        )
        assert resp.status_code == HTTP_NOT_FOUND


class TestAudit:
    async def test_audit_list_finds_a_recorded_action(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        await client.post(
            "/notifications",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"user_id": "user-1", "body": "Hi", "source_service": "test-suite"},
        )
        resp = await client.get(
            "/notifications/audit", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        actions = {row["action"] for row in resp.json()["data"]}
        assert "notification_created" in actions

    async def test_audit_list_filters_by_action(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        await client.post(
            "/notifications",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"user_id": "user-1", "body": "Hi", "source_service": "test-suite"},
        )
        matching = await client.get(
            "/notifications/audit",
            params={"organization_id": str(organization_id), "action": "notification_created"},
        )
        assert len(matching.json()["data"]) >= 1
        non_matching = await client.get(
            "/notifications/audit",
            params={"organization_id": str(organization_id), "action": "template_created"},
        )
        assert non_matching.json()["data"] == []

    async def test_audit_summary_counts_by_action(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        await client.post(
            "/notifications",
            params={"organization_id": str(organization_id)},
            headers=auth_headers(uuid.uuid4()),
            json={"user_id": "user-1", "body": "Hi", "source_service": "test-suite"},
        )
        resp = await client.get(
            "/notifications/audit/summary", params={"organization_id": str(organization_id)}
        )
        assert resp.status_code == HTTP_OK
        data = resp.json()["data"]
        assert data["total"] >= 1
        assert data["by_action"].get("notification_created", 0) >= 1

    async def test_audit_summary_accepts_days(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        resp = await client.get(
            "/notifications/audit/summary",
            params={"organization_id": str(organization_id), "days": 1},
        )
        assert resp.status_code == HTTP_OK
