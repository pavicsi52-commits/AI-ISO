"""Statistics, reports, and the audit trail (docs/056 "REPORTING", "AUDIT LOGGING")."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.models.enums import AuditAction, ReportFormat, ReportKind, ReportStatus
from app.models.governance import ApiReport
from app.models.request import ApiRequestLog, ApiResponseLog
from app.repositories.governance import ApiReportRepository
from app.services.reporting import AuditService, StatisticsService

pytestmark = pytest.mark.asyncio


async def _seed_request_response(
    request_logs_repo, response_logs_repo, organization_id: uuid.UUID, *, status_code: int = 200
) -> None:
    now = datetime.now(UTC)
    request = await request_logs_repo.create(
        ApiRequestLog(
            organization_id=organization_id,
            method="GET",
            path="/echo",
            correlation_id=str(uuid.uuid4()),
            started_at=now,
        )
    )
    await response_logs_repo.create(
        ApiResponseLog(
            organization_id=organization_id,
            request_id=request.id,
            status_code=status_code,
            latency_ms=10.0,
            completed_at=now,
        )
    )


class TestGetStatistics:
    async def test_with_no_data_returns_defaults(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/gateway/statistics", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["responses_by_status_code"] == {}
        assert data["latest_window"]["error_rate"] is None

    async def test_reflects_raw_response_counts_before_any_rollup(
        self, client: AsyncClient, request_logs_repo, response_logs_repo, organization_id: uuid.UUID
    ) -> None:
        await _seed_request_response(
            request_logs_repo, response_logs_repo, organization_id, status_code=200
        )
        await _seed_request_response(
            request_logs_repo, response_logs_repo, organization_id, status_code=500
        )

        response = await client.get(
            "/gateway/statistics", params={"organization_id": str(organization_id)}
        )
        data = response.json()["data"]
        assert data["responses_by_status_code"] == {"200": 1, "500": 1}
        assert data["latest_window"]["error_rate"] is None  # no rollup has run yet

    async def test_latest_window_reflects_the_most_recent_rollup(
        self,
        client: AsyncClient,
        request_logs_repo,
        response_logs_repo,
        statistics_service: StatisticsService,
        organization_id: uuid.UUID,
    ) -> None:
        await _seed_request_response(request_logs_repo, response_logs_repo, organization_id)
        now = datetime.now(UTC)
        await statistics_service.rollup(
            organization_id,
            window_start=now - timedelta(hours=1),
            window_end=now + timedelta(hours=1),
        )

        response = await client.get(
            "/gateway/statistics", params={"organization_id": str(organization_id)}
        )
        latest = response.json()["data"]["latest_window"]
        assert latest["error_rate"] == 0.0
        assert latest["success_rate"] == 100.0
        assert latest["computed_through"] is not None


class TestStatisticsTrend:
    async def test_a_window_outside_since_days_is_excluded(
        self, client: AsyncClient, statistics_service: StatisticsService, organization_id: uuid.UUID
    ) -> None:
        old_moment = datetime.now(UTC) - timedelta(days=90)
        await statistics_service.rollup(
            organization_id, window_start=old_moment, window_end=old_moment + timedelta(hours=1)
        )
        response = await client.get(
            "/gateway/statistics/trend",
            params={"organization_id": str(organization_id), "since_days": 30},
        )
        assert response.json()["data"] == []

    async def test_a_recent_window_is_included(
        self, client: AsyncClient, statistics_service: StatisticsService, organization_id: uuid.UUID
    ) -> None:
        recent_moment = datetime.now(UTC) - timedelta(hours=2)
        await statistics_service.rollup(
            organization_id,
            window_start=recent_moment,
            window_end=recent_moment + timedelta(hours=1),
        )
        response = await client.get(
            "/gateway/statistics/trend",
            params={"organization_id": str(organization_id), "since_days": 30},
        )
        rows = response.json()["data"]
        assert len(rows) == 1

    async def test_an_out_of_range_since_days_is_rejected(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/gateway/statistics/trend",
            params={"organization_id": str(organization_id), "since_days": 0},
        )
        # This platform's own global exception handler maps a FastAPI
        # `RequestValidationError` to `ValidationError`, whose own
        # `status_code` is 400 -- not FastAPI's stock 422.
        assert response.status_code == 400


class TestReportsCrud:
    async def test_list_reports_is_empty_initially(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            "/gateway/reports", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == 200
        assert response.json()["data"] == []

    async def test_generating_a_report_requires_authentication(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/gateway/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "api_usage"},
        )
        assert response.status_code == 401

    async def test_generate_then_list_then_get_a_report(
        self,
        client: AsyncClient,
        auth_headers,
        request_logs_repo,
        response_logs_repo,
        organization_id: uuid.UUID,
    ) -> None:
        await _seed_request_response(request_logs_repo, response_logs_repo, organization_id)
        user_id = uuid.uuid4()

        created = await client.post(
            "/gateway/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "api_usage", "report_format": "csv", "title": "Usage report"},
            headers=auth_headers(user_id),
        )
        assert created.status_code == 201
        report = created.json()["data"]
        assert report["kind"] == "api_usage"
        assert report["status"] == "completed"
        assert report["row_count"] == 1

        listed = await client.get(
            "/gateway/reports", params={"organization_id": str(organization_id)}
        )
        assert [row["id"] for row in listed.json()["data"]] == [report["id"]]

        fetched = await client.get(
            f"/gateway/reports/{report['id']}", params={"organization_id": str(organization_id)}
        )
        assert fetched.status_code == 200
        assert fetched.json()["data"]["id"] == report["id"]

    async def test_generating_a_report_records_an_audit_entry(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        user_id = uuid.uuid4()
        created = await client.post(
            "/gateway/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "audit"},
            headers=auth_headers(user_id),
        )
        report_id = created.json()["data"]["id"]

        audit = await client.get("/gateway/audit", params={"organization_id": str(organization_id)})
        entries = audit.json()["data"]
        assert any(
            entry["entity_id"] == report_id
            and entry["action"] == "administrative"
            and entry["succeeded"]
            for entry in entries
        )

    async def test_a_report_kind_with_no_dedicated_builder_still_completes_empty(
        self, client: AsyncClient, auth_headers, organization_id: uuid.UUID
    ) -> None:
        response = await client.post(
            "/gateway/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "quota"},
            headers=auth_headers(uuid.uuid4()),
        )
        data = response.json()["data"]
        assert data["status"] == "completed"
        assert data["row_count"] == 0

    async def test_get_report_404_for_an_unknown_id(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            f"/gateway/reports/{uuid.uuid4()}", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == 404

    async def test_download_report_defaults_to_csv(
        self,
        client: AsyncClient,
        auth_headers,
        request_logs_repo,
        response_logs_repo,
        organization_id: uuid.UUID,
    ) -> None:
        await _seed_request_response(request_logs_repo, response_logs_repo, organization_id)
        created = await client.post(
            "/gateway/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "api_usage"},
            headers=auth_headers(uuid.uuid4()),
        )
        report_id = created.json()["data"]["id"]

        response = await client.get(
            f"/gateway/reports/{report_id}/download",
            params={"organization_id": str(organization_id)},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]
        assert "method" in response.text  # a CSV header row from the api_usage builder

    async def test_download_report_as_markdown(
        self,
        client: AsyncClient,
        auth_headers,
        request_logs_repo,
        response_logs_repo,
        organization_id: uuid.UUID,
    ) -> None:
        await _seed_request_response(request_logs_repo, response_logs_repo, organization_id)
        created = await client.post(
            "/gateway/reports",
            params={"organization_id": str(organization_id)},
            json={"kind": "api_usage", "title": "Markdown report"},
            headers=auth_headers(uuid.uuid4()),
        )
        report_id = created.json()["data"]["id"]

        response = await client.get(
            f"/gateway/reports/{report_id}/download",
            params={"organization_id": str(organization_id), "report_format": "markdown"},
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/markdown")
        assert response.text.startswith("# Markdown report")

    async def test_download_report_404_for_an_unknown_id(
        self, client: AsyncClient, organization_id: uuid.UUID
    ) -> None:
        response = await client.get(
            f"/gateway/reports/{uuid.uuid4()}/download",
            params={"organization_id": str(organization_id)},
        )
        assert response.status_code == 404

    async def test_download_a_report_with_no_content_is_404(
        self, client: AsyncClient, reports_repo: ApiReportRepository, organization_id: uuid.UUID
    ) -> None:
        # A report that never finished (still PENDING) has whatever the
        # `content` column's own default resolves to -- an empty dict,
        # which `download_report` treats as "nothing to download."
        pending = await reports_repo.create(
            ApiReport(
                organization_id=organization_id,
                kind=ReportKind.QUOTA,
                report_format=ReportFormat.CSV,
                title="Still running",
                status=ReportStatus.PENDING,
            )
        )
        response = await client.get(
            f"/gateway/reports/{pending.id}/download",
            params={"organization_id": str(organization_id)},
        )
        assert response.status_code == 404


class TestAuditTrail:
    async def test_lists_entries_newest_first(
        self, client: AsyncClient, audit_service: AuditService, organization_id: uuid.UUID
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.SERVICE_REGISTERED,
            entity_type="service",
            summary="First",
        )
        await audit_service.record(
            organization_id,
            action=AuditAction.ROUTE_CREATED,
            entity_type="route",
            summary="Second",
        )

        response = await client.get(
            "/gateway/audit", params={"organization_id": str(organization_id)}
        )
        assert response.status_code == 200
        entries = response.json()["data"]
        assert [entry["summary"] for entry in entries] == ["Second", "First"]

    async def test_respects_limit_and_offset(
        self, client: AsyncClient, audit_service: AuditService, organization_id: uuid.UUID
    ) -> None:
        for i in range(3):
            await audit_service.record(
                organization_id,
                action=AuditAction.ADMINISTRATIVE,
                entity_type="service",
                summary=f"Entry {i}",
            )
        response = await client.get(
            "/gateway/audit",
            params={"organization_id": str(organization_id), "limit": 1, "offset": 1},
        )
        assert len(response.json()["data"]) == 1
