"""``app/api/analytics.py`` -- org-wide connector health dashboard, statistics,
generated reports, and the audit trail.

Against the real FastAPI app (``tests/conftest.py``'s own ``client`` fixture,
started through its actual lifespan) with only the request's own database
session and outbound HTTP client substituted -- see ``tests/conftest.py``'s
module docstring.

**``GET /integrations/health`` is this router's own org-wide connector health
dashboard, not the bare service-level ``/health`` liveness route** exercised
in ``tests/test_smoke.py`` -- two different routers, same word.

Only ``POST /integrations/reports`` takes a ``CurrentUserId`` dependency -- it
is the one mutating route in this router and records an audit entry like
every other mutating route in this service. Every other route here (the
health dashboard, statistics, trend, list/get/download reports, the audit
trail itself) is read-only and needs no ``Authorization`` header.

The health-dashboard probe uses PostgreSQL's own published port
(``REACHABLE_TCP_HOST``/``REACHABLE_TCP_PORT``) as a genuinely reachable TCP
endpoint -- the same "point a reachability check at a real already-running
container" precedent this service's own ``tests/conftest.py`` documents,
since ``HealthService.probe`` calls ``shared_core.monitoring.checks
.check_tcp_reachable`` directly and cannot be pointed at a test double.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.models.enums import AuditAction, ReportFormat, ReportKind, ReportStatus, SyncStatus
from app.models.governance import ConnectorReport
from app.models.sync import ConnectorSyncJob
from tests.conftest import (
    HTTP_BAD_REQUEST,
    HTTP_CREATED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    REACHABLE_TCP_HOST,
    REACHABLE_TCP_PORT,
    ago,
    utcnow,
)


class TestConnectorHealthDashboardEndpoint:
    async def test_shows_unknown_for_connectors_that_have_never_been_probed(
        self, client, make_connector, organization_id
    ) -> None:
        await make_connector("connector-one")
        await make_connector("connector-two")

        response = await client.get(
            "/integrations/health", params={"organization_id": str(organization_id)}
        )

        assert response.status_code == HTTP_OK
        rows = response.json()["data"]
        assert len(rows) == 2
        assert all(row["status"] == "unknown" for row in rows)
        assert all(row["checked_at"] is None for row in rows)

    async def test_shows_the_real_latest_status_for_a_probed_connector(
        self, client, connector_service, health_service, make_connector, organization_id
    ) -> None:
        probed = await make_connector("probed-connector")
        await make_connector("unprobed-connector")
        configured = await connector_service.configure(
            organization_id,
            probed.id,
            config={"host": REACHABLE_TCP_HOST, "port": REACHABLE_TCP_PORT},
        )
        health_row = await health_service.probe(configured)
        assert health_row.status == "healthy"  # confirms this is a genuine, non-degenerate probe

        response = await client.get(
            "/integrations/health", params={"organization_id": str(organization_id)}
        )

        assert response.status_code == HTTP_OK
        rows = {row["name"]: row for row in response.json()["data"]}
        assert rows["probed-connector"]["status"] == "healthy"
        assert rows["probed-connector"]["connector_id"] == str(probed.id)
        assert rows["probed-connector"]["checked_at"] == health_row.checked_at.isoformat()
        assert rows["unprobed-connector"]["status"] == "unknown"
        assert rows["unprobed-connector"]["checked_at"] is None

    async def test_is_tenant_scoped(self, client, make_connector, organization_id) -> None:
        await make_connector("in-this-org")

        response = await client.get(
            "/integrations/health", params={"organization_id": str(uuid.uuid4())}
        )

        assert response.status_code == HTTP_OK
        assert response.json()["data"] == []

    async def test_a_missing_organization_id_is_rejected(self, client) -> None:
        response = await client.get("/integrations/health")

        assert response.status_code == HTTP_BAD_REQUEST


class TestGetStatisticsEndpoint:
    async def test_returns_nulls_when_no_window_has_ever_been_computed(
        self, client, organization_id
    ) -> None:
        response = await client.get(
            "/integrations/statistics", params={"organization_id": str(organization_id)}
        )

        assert response.status_code == HTTP_OK
        window = response.json()["data"]["latest_window"]
        assert window["syncs_attempted"] is None
        assert window["success_rate"] is None
        assert window["records_processed"] is None
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
            "/integrations/statistics", params={"organization_id": str(organization_id)}
        )

        assert response.status_code == HTTP_OK
        window = response.json()["data"]["latest_window"]
        assert window["syncs_attempted"] == latest.syncs_attempted
        assert window["success_rate"] == latest.success_rate
        assert window["records_processed"] == latest.records_processed
        assert window["computed_through"] == latest.window_end.isoformat()

    async def test_is_tenant_scoped(self, client, statistics_service, organization_id) -> None:
        await statistics_service.rollup(
            organization_id, window_start=ago(3_600), window_end=utcnow()
        )

        response = await client.get(
            "/integrations/statistics", params={"organization_id": str(uuid.uuid4())}
        )

        assert response.status_code == HTTP_OK
        assert response.json()["data"]["latest_window"]["computed_through"] is None

    async def test_a_missing_organization_id_is_rejected(self, client) -> None:
        response = await client.get("/integrations/statistics")

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
            "/integrations/statistics/trend", params={"organization_id": str(organization_id)}
        )

        assert response.status_code == HTTP_OK
        body = response.json()["data"]
        assert [row["id"] for row in body] == [str(older.id), str(newer.id)]

    async def test_empty_when_no_window_has_ever_been_computed(
        self, client, organization_id
    ) -> None:
        response = await client.get(
            "/integrations/statistics/trend", params={"organization_id": str(organization_id)}
        )

        assert response.status_code == HTTP_OK
        assert response.json()["data"] == []

    async def test_since_days_excludes_older_windows(
        self, client, statistics_service, organization_id
    ) -> None:
        old_start = ago(90 * 24 * 3_600)
        await statistics_service.rollup(
            organization_id, window_start=old_start, window_end=old_start + timedelta(hours=1)
        )

        response = await client.get(
            "/integrations/statistics/trend",
            params={"organization_id": str(organization_id), "since_days": 1},
        )

        assert response.status_code == HTTP_OK
        assert response.json()["data"] == []

    async def test_an_out_of_range_since_days_is_rejected(self, client, organization_id) -> None:
        response = await client.get(
            "/integrations/statistics/trend",
            params={"organization_id": str(organization_id), "since_days": 0},
        )

        assert response.status_code == HTTP_BAD_REQUEST


class TestListReportsEndpoint:
    async def test_lists_every_report_in_the_organization_newest_first(
        self, client, report_service, organization_id
    ) -> None:
        first = await report_service.generate(organization_id, kind=ReportKind.CONNECTOR)
        second = await report_service.generate(organization_id, kind=ReportKind.AUDIT)

        response = await client.get(
            "/integrations/reports", params={"organization_id": str(organization_id)}
        )

        assert response.status_code == HTTP_OK
        body = response.json()["data"]
        assert [row["id"] for row in body] == [str(second.id), str(first.id)]

    async def test_is_tenant_scoped(self, client, report_service, organization_id) -> None:
        await report_service.generate(organization_id, kind=ReportKind.CONNECTOR)

        response = await client.get(
            "/integrations/reports", params={"organization_id": str(uuid.uuid4())}
        )

        assert response.status_code == HTTP_OK
        assert response.json()["data"] == []

    async def test_respects_limit_and_offset_query_params(
        self, client, report_service, organization_id
    ) -> None:
        reports = [
            await report_service.generate(organization_id, kind=ReportKind.CONNECTOR)
            for _ in range(3)
        ]

        response = await client.get(
            "/integrations/reports",
            params={"organization_id": str(organization_id), "limit": 1, "offset": 1},
        )

        assert response.status_code == HTTP_OK
        body = response.json()["data"]
        assert len(body) == 1
        assert body[0]["id"] == str(reports[1].id)


class TestGenerateReportEndpoint:
    """One test per real-builder kind (``connector``/``synchronization``/
    ``health``/``audit`` -- ``ReportService._BUILDERS``), plus the three
    empty-builder kinds (``credential``/``marketplace``/``performance``),
    which must still complete successfully with zero rows rather than fail.
    """

    async def test_connector_report_has_real_rows(
        self, client, auth_headers, make_connector, organization_id
    ) -> None:
        await make_connector("report-connector")

        response = await client.post(
            "/integrations/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "connector"},
            headers=auth_headers(uuid.uuid4()),
        )

        assert response.status_code == HTTP_CREATED, response.text
        data = response.json()["data"]
        assert data["kind"] == "connector"
        assert data["status"] == "completed"
        assert data["row_count"] == 1
        assert data["content"]["rows"][0]["name"] == "report-connector"

    async def test_synchronization_report_has_real_rows(
        self, client, auth_headers, sync_jobs_repo, make_connector, organization_id
    ) -> None:
        connector = await make_connector()
        await sync_jobs_repo.create(
            ConnectorSyncJob(
                organization_id=organization_id,
                connector_id=connector.id,
                status=SyncStatus.COMPLETED,
                records_processed=4,
                records_failed=1,
                created_at=utcnow(),
            )
        )

        response = await client.post(
            "/integrations/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "synchronization"},
            headers=auth_headers(uuid.uuid4()),
        )

        assert response.status_code == HTTP_CREATED, response.text
        data = response.json()["data"]
        assert data["row_count"] == 1
        row = data["content"]["rows"][0]
        assert row["connector_id"] == str(connector.id)
        assert row["records_processed"] == 4
        assert row["records_failed"] == 1

    async def test_health_report_has_real_rows(
        self,
        client,
        auth_headers,
        connector_service,
        health_service,
        make_connector,
        organization_id,
    ) -> None:
        connector = await make_connector("probed-connector")
        configured = await connector_service.configure(
            organization_id,
            connector.id,
            config={"host": REACHABLE_TCP_HOST, "port": REACHABLE_TCP_PORT},
        )
        await health_service.probe(configured)

        response = await client.post(
            "/integrations/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "health"},
            headers=auth_headers(uuid.uuid4()),
        )

        assert response.status_code == HTTP_CREATED, response.text
        data = response.json()["data"]
        assert data["row_count"] == 1
        row = data["content"]["rows"][0]
        assert row["connector_id"] == str(connector.id)
        assert row["status"] == "healthy"

    async def test_audit_report_has_real_rows(
        self, client, auth_headers, audit_service, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.CONNECTOR_REGISTERED,
            entity_type="connector",
            summary="Registered.",
        )

        response = await client.post(
            "/integrations/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "audit"},
            headers=auth_headers(uuid.uuid4()),
        )

        assert response.status_code == HTTP_CREATED, response.text
        data = response.json()["data"]
        assert data["row_count"] == 1
        assert data["content"]["rows"][0]["action"] == "connector_registered"

    @pytest.mark.parametrize("kind", ["credential", "marketplace", "performance"])
    async def test_kinds_with_no_builder_still_complete_with_zero_rows(
        self, client, auth_headers, organization_id, kind: str
    ) -> None:
        response = await client.post(
            "/integrations/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": kind},
            headers=auth_headers(uuid.uuid4()),
        )

        assert response.status_code == HTTP_CREATED, response.text
        data = response.json()["data"]
        assert data["kind"] == kind
        assert data["status"] == "completed"
        assert data["row_count"] == 0
        assert data["content"] == {"rows": []}

    async def test_defaults_the_title_from_the_report_kind(
        self, client, auth_headers, organization_id
    ) -> None:
        response = await client.post(
            "/integrations/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "connector"},
            headers=auth_headers(uuid.uuid4()),
        )

        assert response.json()["data"]["title"] == "connector report"

    async def test_generated_by_is_the_authenticated_caller(
        self, client, auth_headers, organization_id
    ) -> None:
        caller = uuid.uuid4()

        response = await client.post(
            "/integrations/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "connector"},
            headers=auth_headers(caller),
        )

        assert response.json()["data"]["generated_by"] == str(caller)

    async def test_writes_an_audit_entry_for_the_generation_itself(
        self, client, auth_headers, organization_id
    ) -> None:
        caller = uuid.uuid4()
        await client.post(
            "/integrations/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "connector"},
            headers=auth_headers(caller),
        )

        response = await client.get(
            "/integrations/audit", params={"organization_id": str(organization_id)}
        )

        entries = response.json()["data"]
        assert any(
            entry["action"] == "administrative" and entry["actor_id"] == str(caller)
            for entry in entries
        )

    async def test_401_without_authentication(self, client, organization_id) -> None:
        response = await client.post(
            "/integrations/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "connector"},
        )

        assert response.status_code == 401

    async def test_an_invalid_kind_is_rejected(self, client, auth_headers, organization_id) -> None:
        response = await client.post(
            "/integrations/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "not-a-real-kind"},
            headers=auth_headers(uuid.uuid4()),
        )

        assert response.status_code == HTTP_BAD_REQUEST


class TestGetReportEndpoint:
    async def test_returns_the_report(self, client, report_service, organization_id) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.CONNECTOR)

        response = await client.get(
            f"/integrations/reports/{report.id}", params={"organization_id": str(organization_id)}
        )

        assert response.status_code == HTTP_OK
        assert response.json()["data"]["id"] == str(report.id)

    async def test_404_for_an_unknown_report_id(self, client, organization_id) -> None:
        response = await client.get(
            f"/integrations/reports/{uuid.uuid4()}",
            params={"organization_id": str(organization_id)},
        )

        assert response.status_code == HTTP_NOT_FOUND

    async def test_404_when_the_report_belongs_to_a_different_org(
        self, client, report_service, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.CONNECTOR)

        response = await client.get(
            f"/integrations/reports/{report.id}", params={"organization_id": str(uuid.uuid4())}
        )

        assert response.status_code == HTTP_NOT_FOUND


class TestDownloadReportEndpoint:
    async def test_downloads_a_completed_report_as_csv_by_default(
        self, client, report_service, audit_service, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.CONNECTOR_REGISTERED,
            entity_type="connector",
            summary="seed row",
        )
        report = await report_service.generate(organization_id, kind=ReportKind.AUDIT)

        response = await client.get(
            f"/integrations/reports/{report.id}/download",
            params={"organization_id": str(organization_id)},
        )

        assert response.status_code == HTTP_OK
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]
        assert f"audit-{report.id}.csv" in response.headers["content-disposition"]
        assert "connector_registered" in response.text
        assert "seed row" not in response.text  # summary isn't one of the audit report's columns

    async def test_downloads_as_markdown_when_requested(
        self, client, report_service, audit_service, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.CONNECTOR_REGISTERED,
            entity_type="connector",
            summary="seed row",
        )
        report = await report_service.generate(organization_id, kind=ReportKind.AUDIT)

        response = await client.get(
            f"/integrations/reports/{report.id}/download",
            params={"organization_id": str(organization_id), "report_format": "markdown"},
        )

        assert response.status_code == HTTP_OK
        assert response.headers["content-type"].startswith("text/markdown")
        assert f"audit-{report.id}.md" in response.headers["content-disposition"]
        assert response.text.startswith("# audit report")
        assert "connector_registered" in response.text

    async def test_404_when_the_report_has_no_content_yet(
        self, client, reports_repo, organization_id
    ) -> None:
        still_running = await reports_repo.create(
            ConnectorReport(
                organization_id=organization_id,
                kind=ReportKind.CONNECTOR,
                report_format=ReportFormat.JSON,
                title="still running",
                status=ReportStatus.RUNNING,
            )
        )

        response = await client.get(
            f"/integrations/reports/{still_running.id}/download",
            params={"organization_id": str(organization_id)},
        )

        assert response.status_code == HTTP_NOT_FOUND

    async def test_404_for_an_unknown_report_id(self, client, organization_id) -> None:
        response = await client.get(
            f"/integrations/reports/{uuid.uuid4()}/download",
            params={"organization_id": str(organization_id)},
        )

        assert response.status_code == HTTP_NOT_FOUND


class TestListAuditEndpoint:
    async def test_lists_entries_newest_first(self, client, audit_service, organization_id) -> None:
        first = await audit_service.record(
            organization_id,
            action=AuditAction.CONNECTOR_REGISTERED,
            entity_type="connector",
            summary="first",
        )
        second = await audit_service.record(
            organization_id,
            action=AuditAction.CONNECTOR_ENABLED,
            entity_type="connector",
            summary="second",
        )

        response = await client.get(
            "/integrations/audit", params={"organization_id": str(organization_id)}
        )

        assert response.status_code == HTTP_OK
        body = response.json()["data"]
        assert [row["id"] for row in body] == [str(second.id), str(first.id)]

    async def test_is_tenant_scoped(self, client, audit_service, organization_id) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.ADMINISTRATIVE,
            entity_type="connector",
            summary="in this org",
        )

        response = await client.get(
            "/integrations/audit", params={"organization_id": str(uuid.uuid4())}
        )

        assert response.status_code == HTTP_OK
        assert response.json()["data"] == []

    async def test_respects_limit_and_offset_query_params(
        self, client, audit_service, organization_id
    ) -> None:
        entries = [
            await audit_service.record(
                organization_id,
                action=AuditAction.ADMINISTRATIVE,
                entity_type="connector",
                summary=f"entry {i}",
            )
            for i in range(3)
        ]

        response = await client.get(
            "/integrations/audit",
            params={"organization_id": str(organization_id), "limit": 1, "offset": 1},
        )

        assert response.status_code == HTTP_OK
        body = response.json()["data"]
        assert len(body) == 1
        # Newest first: offset 1 skips the most recently written entry.
        assert body[0]["id"] == str(entries[1].id)

    async def test_a_missing_organization_id_is_rejected(self, client) -> None:
        response = await client.get("/integrations/audit")

        assert response.status_code == HTTP_BAD_REQUEST
