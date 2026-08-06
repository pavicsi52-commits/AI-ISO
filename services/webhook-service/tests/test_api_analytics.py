"""``app/api/analytics.py`` -- statistics, generated reports, and the audit trail.

Against the real FastAPI app (``tests/conftest.py``'s own ``client`` fixture,
started through its actual lifespan) with only the request's own database
session and outbound HTTP client substituted -- see ``tests/conftest.py``'s
module docstring.

Only ``POST /webhooks/reports`` takes a ``CurrentUserId`` dependency -- it is
the one mutating route in this router and records an audit entry like every
other mutating route in this service. Every other route here (statistics,
trend, list/get/download reports, the audit trail itself) is read-only and
needs no ``Authorization`` header, consistent with every other read-style
route across this API.
"""

from __future__ import annotations

import uuid

from app.models.enums import ReportFormat, ReportKind, ReportStatus
from app.models.governance import WebhookReport
from tests.conftest import HTTP_BAD_REQUEST, HTTP_CREATED, HTTP_NOT_FOUND, HTTP_OK, ago, utcnow


class TestGetStatisticsEndpoint:
    async def test_returns_nulls_when_no_window_has_ever_been_computed(
        self, client, organization_id
    ) -> None:
        response = await client.get(
            "/webhooks/statistics", params={"organization_id": str(organization_id)}
        )

        assert response.status_code == HTTP_OK
        window = response.json()["data"]["latest_window"]
        assert window["deliveries_attempted"] is None
        assert window["success_rate"] is None
        assert window["computed_through"] is None

    async def test_returns_the_most_recently_computed_window(
        self, client, statistics_service, organization_id
    ) -> None:
        await statistics_service.rollup(
            organization_id, window_start=ago(7_200), window_end=ago(3_600)
        )
        latest = await statistics_service.rollup(
            organization_id, window_start=ago(3_600), window_end=utcnow()
        )

        response = await client.get(
            "/webhooks/statistics", params={"organization_id": str(organization_id)}
        )

        window = response.json()["data"]["latest_window"]
        assert window["success_rate"] == latest.success_rate
        assert window["computed_through"] == latest.window_end.isoformat()

    async def test_is_tenant_scoped(self, client, statistics_service, organization_id) -> None:
        await statistics_service.rollup(
            organization_id, window_start=ago(3_600), window_end=utcnow()
        )

        response = await client.get(
            "/webhooks/statistics", params={"organization_id": str(uuid.uuid4())}
        )

        assert response.json()["data"]["latest_window"]["computed_through"] is None

    async def test_a_missing_organization_id_is_rejected(self, client) -> None:
        response = await client.get("/webhooks/statistics")

        assert response.status_code == HTTP_BAD_REQUEST


class TestGetStatisticsTrendEndpoint:
    async def test_lists_windows_oldest_first(
        self, client, statistics_service, organization_id
    ) -> None:
        older = await statistics_service.rollup(
            organization_id, window_start=ago(7_200), window_end=ago(3_600)
        )
        newer = await statistics_service.rollup(
            organization_id, window_start=ago(3_600), window_end=utcnow()
        )

        response = await client.get(
            "/webhooks/statistics/trend", params={"organization_id": str(organization_id)}
        )

        assert response.status_code == HTTP_OK
        body = response.json()["data"]
        assert [row["id"] for row in body] == [str(older.id), str(newer.id)]

    async def test_empty_when_no_window_has_ever_been_computed(
        self, client, organization_id
    ) -> None:
        response = await client.get(
            "/webhooks/statistics/trend", params={"organization_id": str(organization_id)}
        )

        assert response.json()["data"] == []

    async def test_an_out_of_range_since_days_is_rejected(self, client, organization_id) -> None:
        response = await client.get(
            "/webhooks/statistics/trend",
            params={"organization_id": str(organization_id), "since_days": 0},
        )

        assert response.status_code == HTTP_BAD_REQUEST


class TestListReportsEndpoint:
    async def test_lists_every_report_in_the_organization_newest_first(
        self, client, report_service, organization_id
    ) -> None:
        first = await report_service.generate(organization_id, kind=ReportKind.AUDIT)
        second = await report_service.generate(organization_id, kind=ReportKind.DELIVERY)

        response = await client.get(
            "/webhooks/reports", params={"organization_id": str(organization_id)}
        )

        assert response.status_code == HTTP_OK
        body = response.json()["data"]
        assert [row["id"] for row in body] == [str(second.id), str(first.id)]

    async def test_is_tenant_scoped(self, client, report_service, organization_id) -> None:
        await report_service.generate(organization_id, kind=ReportKind.AUDIT)

        response = await client.get(
            "/webhooks/reports", params={"organization_id": str(uuid.uuid4())}
        )

        assert response.json()["data"] == []

    async def test_respects_the_limit_query_param(
        self, client, report_service, organization_id
    ) -> None:
        for _ in range(3):
            await report_service.generate(organization_id, kind=ReportKind.AUDIT)

        response = await client.get(
            "/webhooks/reports", params={"organization_id": str(organization_id), "limit": 2}
        )

        assert len(response.json()["data"]) == 2


class TestGenerateReportEndpoint:
    async def test_generates_and_stores_a_completed_report(
        self, client, auth_headers, organization_id
    ) -> None:
        caller = uuid.uuid4()

        response = await client.post(
            "/webhooks/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "audit", "report_format": "json"},
            headers=auth_headers(caller),
        )

        assert response.status_code == HTTP_CREATED
        data = response.json()["data"]
        assert data["kind"] == "audit"
        assert data["status"] == "completed"
        assert data["generated_by"] == str(caller)
        assert data["row_count"] == 0

    async def test_defaults_the_title_from_the_report_kind(
        self, client, auth_headers, organization_id
    ) -> None:
        response = await client.post(
            "/webhooks/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "delivery"},
            headers=auth_headers(uuid.uuid4()),
        )

        assert response.json()["data"]["title"] == "delivery report"

    async def test_writes_an_audit_entry_for_the_generation_itself(
        self, client, auth_headers, organization_id
    ) -> None:
        caller = uuid.uuid4()
        await client.post(
            "/webhooks/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "audit"},
            headers=auth_headers(caller),
        )

        response = await client.get(
            "/webhooks/audit", params={"organization_id": str(organization_id)}
        )

        entries = response.json()["data"]
        assert any(
            entry["action"] == "administrative" and entry["actor_id"] == str(caller)
            for entry in entries
        )

    async def test_401_without_authentication(self, client, organization_id) -> None:
        response = await client.post(
            "/webhooks/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "audit"},
        )

        assert response.status_code == 401

    async def test_an_invalid_kind_is_rejected(self, client, auth_headers, organization_id) -> None:
        response = await client.post(
            "/webhooks/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "not-a-real-kind"},
            headers=auth_headers(uuid.uuid4()),
        )

        assert response.status_code == HTTP_BAD_REQUEST


class TestGetReportEndpoint:
    async def test_returns_the_report(self, client, report_service, organization_id) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.AUDIT)

        response = await client.get(
            f"/webhooks/reports/{report.id}", params={"organization_id": str(organization_id)}
        )

        assert response.status_code == HTTP_OK
        assert response.json()["data"]["id"] == str(report.id)

    async def test_404_for_an_unknown_report_id(self, client, organization_id) -> None:
        response = await client.get(
            f"/webhooks/reports/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )

        assert response.status_code == HTTP_NOT_FOUND

    async def test_404_when_the_report_belongs_to_a_different_org(
        self, client, report_service, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.AUDIT)

        response = await client.get(
            f"/webhooks/reports/{report.id}", params={"organization_id": str(uuid.uuid4())}
        )

        assert response.status_code == HTTP_NOT_FOUND


class TestDownloadReportEndpoint:
    async def test_downloads_a_completed_report_as_csv_by_default(
        self, client, report_service, audit_service, organization_id
    ) -> None:
        await audit_service.record(
            organization_id, action="administrative", entity_type="report", summary="seed row"
        )
        report = await report_service.generate(organization_id, kind=ReportKind.AUDIT)

        response = await client.get(
            f"/webhooks/reports/{report.id}/download",
            params={"organization_id": str(organization_id)},
        )

        assert response.status_code == HTTP_OK
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]
        assert "seed row" not in response.text  # summary isn't one of the audit report's columns
        assert "administrative" in response.text

    async def test_downloads_as_markdown_when_requested(
        self, client, report_service, audit_service, organization_id
    ) -> None:
        await audit_service.record(
            organization_id, action="administrative", entity_type="report", summary="seed row"
        )
        report = await report_service.generate(organization_id, kind=ReportKind.AUDIT)

        response = await client.get(
            f"/webhooks/reports/{report.id}/download",
            params={"organization_id": str(organization_id), "report_format": "markdown"},
        )

        assert response.status_code == HTTP_OK
        assert response.headers["content-type"].startswith("text/markdown")
        assert response.text.startswith("# audit report")

    async def test_404_when_the_report_has_no_content_yet(
        self, client, reports_repo, organization_id
    ) -> None:
        still_running = await reports_repo.create(
            WebhookReport(
                organization_id=organization_id,
                kind=ReportKind.DELIVERY,
                report_format=ReportFormat.JSON,
                title="still running",
                status=ReportStatus.RUNNING,
            )
        )

        response = await client.get(
            f"/webhooks/reports/{still_running.id}/download",
            params={"organization_id": str(organization_id)},
        )

        assert response.status_code == HTTP_NOT_FOUND

    async def test_404_for_an_unknown_report_id(self, client, organization_id) -> None:
        response = await client.get(
            f"/webhooks/reports/{uuid.uuid4()}/download",
            params={"organization_id": str(organization_id)},
        )

        assert response.status_code == HTTP_NOT_FOUND


class TestListAuditEndpoint:
    async def test_lists_entries_newest_first(self, client, audit_service, organization_id) -> None:
        first = await audit_service.record(
            organization_id, action="administrative", entity_type="report", summary="first"
        )
        second = await audit_service.record(
            organization_id, action="administrative", entity_type="report", summary="second"
        )

        response = await client.get(
            "/webhooks/audit", params={"organization_id": str(organization_id)}
        )

        assert response.status_code == HTTP_OK
        body = response.json()["data"]
        assert [row["id"] for row in body][:2] == [str(second.id), str(first.id)]

    async def test_is_tenant_scoped(self, client, audit_service, organization_id) -> None:
        await audit_service.record(
            organization_id, action="administrative", entity_type="report", summary="in this org"
        )

        response = await client.get(
            "/webhooks/audit", params={"organization_id": str(uuid.uuid4())}
        )

        assert response.json()["data"] == []

    async def test_respects_the_limit_query_param(
        self, client, audit_service, organization_id
    ) -> None:
        for i in range(3):
            await audit_service.record(
                organization_id, action="administrative", entity_type="report", summary=f"entry {i}"
            )

        response = await client.get(
            "/webhooks/audit", params={"organization_id": str(organization_id), "limit": 2}
        )

        assert len(response.json()["data"]) == 2

    async def test_a_missing_organization_id_is_rejected(self, client) -> None:
        response = await client.get("/webhooks/audit")

        assert response.status_code == HTTP_BAD_REQUEST
