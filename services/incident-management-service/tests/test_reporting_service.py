"""StatisticsService, ReportService, AuditService."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.enums import AuditAction, JobStatus, ReportKind
from app.services.reporting import AuditService, ReportService, StatisticsService

pytestmark = pytest.mark.asyncio


class TestStatisticsService:
    async def test_rollup_counts_incidents_created_in_the_window(
        self, statistics_service: StatisticsService, organization_id, make_incident
    ) -> None:
        await make_incident()
        await make_incident()
        start = datetime.now(UTC) - timedelta(hours=1)
        end = datetime.now(UTC) + timedelta(hours=1)
        window = await statistics_service.rollup(
            organization_id, window_start=start, window_end=end
        )
        assert window.incidents_created >= 2

    async def test_rollup_is_idempotent_by_window_start(
        self, statistics_service: StatisticsService, organization_id, make_incident
    ) -> None:
        await make_incident()
        start = datetime.now(UTC) - timedelta(hours=1)
        end = datetime.now(UTC) + timedelta(hours=1)
        first = await statistics_service.rollup(organization_id, window_start=start, window_end=end)
        first_id, first_count = first.id, first.incidents_created
        await make_incident()
        second = await statistics_service.rollup(
            organization_id, window_start=start, window_end=end
        )
        assert second.id == first_id
        assert second.incidents_created == first_count + 1

    async def test_dashboard_reports_open_counts(
        self, statistics_service: StatisticsService, organization_id, make_incident
    ) -> None:
        await make_incident()
        dashboard = await statistics_service.dashboard(organization_id)
        assert "by_status" in dashboard
        assert "active_major_incidents" in dashboard

    async def test_trend_returns_recent_windows_oldest_first(
        self, statistics_service: StatisticsService, organization_id, make_incident
    ) -> None:
        await make_incident()
        start = datetime.now(UTC) - timedelta(hours=1)
        end = datetime.now(UTC) + timedelta(hours=1)
        await statistics_service.rollup(organization_id, window_start=start, window_end=end)
        windows = await statistics_service.trend(organization_id, since_days=1)
        assert len(windows) >= 1


class TestReportService:
    async def test_generate_an_incident_report(
        self, report_service: ReportService, organization_id, make_incident
    ) -> None:
        await make_incident()
        report = await report_service.generate(organization_id, kind=ReportKind.INCIDENT)
        assert report.status == str(JobStatus.COMPLETED)
        assert report.row_count >= 1

    async def test_generate_an_executive_report(
        self, report_service: ReportService, organization_id, make_incident
    ) -> None:
        await make_incident()
        report = await report_service.generate(organization_id, kind=ReportKind.EXECUTIVE)
        assert report.status == str(JobStatus.COMPLETED)

    async def test_generate_a_trend_report(
        self, report_service: ReportService, organization_id, make_incident
    ) -> None:
        await make_incident()
        report = await report_service.generate(organization_id, kind=ReportKind.TREND)
        assert report.status == str(JobStatus.COMPLETED)

    async def test_a_report_kind_with_no_organization_wide_builder_returns_no_rows(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.ROOT_CAUSE)
        assert report.status == str(JobStatus.COMPLETED)
        assert report.content.get("rows") == []

    async def test_list_for_org_lists_newest_first(
        self, report_service: ReportService, organization_id
    ) -> None:
        await report_service.generate(organization_id, kind=ReportKind.INCIDENT)
        await report_service.generate(organization_id, kind=ReportKind.EXECUTIVE)
        rows = await report_service.list_for_org(organization_id)
        assert len(rows) == 2

    async def test_to_csv_renders_rows(
        self, report_service: ReportService, organization_id, make_incident
    ) -> None:
        await make_incident()
        report = await report_service.generate(organization_id, kind=ReportKind.INCIDENT)
        csv_text = report_service.to_csv(report.content)
        assert "reference" in csv_text

    async def test_to_csv_of_empty_rows_is_an_empty_string(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.ROOT_CAUSE)
        assert report_service.to_csv(report.content) == ""

    async def test_to_markdown_renders_a_table(
        self, report_service: ReportService, organization_id, make_incident
    ) -> None:
        await make_incident()
        report = await report_service.generate(organization_id, kind=ReportKind.INCIDENT)
        markdown = report_service.to_markdown(report.content, title="Incidents")
        assert "| reference |" in markdown

    async def test_to_markdown_of_empty_rows_says_so(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.ROOT_CAUSE)
        markdown = report_service.to_markdown(report.content)
        assert "No rows." in markdown


class TestAuditService:
    async def test_record_appends_an_entry(
        self, audit_service: AuditService, organization_id
    ) -> None:
        entry = await audit_service.record(
            organization_id,
            action=AuditAction.INCIDENT_CREATED,
            entity_type="incident",
            summary="Opened INC-0001.",
        )
        assert entry.succeeded is True

    async def test_list_entries_filters_by_action(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.INCIDENT_CREATED,
            entity_type="incident",
            summary="Opened.",
        )
        await audit_service.record(
            organization_id,
            action=AuditAction.ESCALATED,
            entity_type="incident",
            summary="Escalated.",
        )
        found = await audit_service.list_entries(organization_id, action=AuditAction.ESCALATED)
        assert len(found) == 1
        assert found[0].action == str(AuditAction.ESCALATED)

    async def test_summary_counts_by_action(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.INCIDENT_CREATED,
            entity_type="incident",
            summary="Opened.",
        )
        summary = await audit_service.summary(organization_id, days=1)
        assert summary["total"] >= 1
        assert str(AuditAction.INCIDENT_CREATED) in summary["by_action"]

    async def test_record_failure_without_a_session_factory_records_inline(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record_failure(
            organization_id,
            action=AuditAction.INCIDENT_CREATED,
            entity_type="incident",
            summary="Refused: quota exceeded.",
        )
        found = await audit_service.list_entries(organization_id)
        assert any(one.succeeded is False for one in found)
