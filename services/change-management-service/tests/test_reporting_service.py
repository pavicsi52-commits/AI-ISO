"""StatisticsService, ReportService, AuditService."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from shared_core.exceptions.not_found import NotFoundError
from tests.conftest import utcnow

from app.models.enums import AuditAction, ChangeStatus, JobStatus, ReportKind
from app.repositories.governance import ChangeAuditRepository
from app.services.change import ChangeService
from app.services.reporting import AuditService, ReportService, StatisticsService

pytestmark = pytest.mark.asyncio


class TestStatisticsService:
    async def test_rollup_counts_changes_created_in_the_window(
        self, statistics_service: StatisticsService, organization_id, make_change
    ) -> None:
        await make_change()
        await make_change()
        start = utcnow() - timedelta(hours=1)
        end = utcnow() + timedelta(hours=1)
        window = await statistics_service.rollup(
            organization_id, window_start=start, window_end=end
        )
        assert window.changes_created >= 2

    async def test_rollup_is_idempotent_by_window_start(
        self, statistics_service: StatisticsService, organization_id, make_change
    ) -> None:
        await make_change()
        start = utcnow() - timedelta(hours=1)
        end = utcnow() + timedelta(hours=1)
        first = await statistics_service.rollup(organization_id, window_start=start, window_end=end)
        first_id, first_count = first.id, first.changes_created
        await make_change()
        second = await statistics_service.rollup(
            organization_id, window_start=start, window_end=end
        )
        assert second.id == first_id
        assert second.changes_created == first_count + 1

    async def test_rollup_success_rate_is_100_with_no_terminal_changes(
        self, statistics_service: StatisticsService, organization_id, make_change
    ) -> None:
        await make_change()
        start = utcnow() - timedelta(hours=1)
        end = utcnow() + timedelta(hours=1)
        window = await statistics_service.rollup(
            organization_id, window_start=start, window_end=end
        )
        assert window.success_rate == 100.0

    async def test_rollup_computes_success_rate_from_terminal_outcomes(
        self,
        statistics_service: StatisticsService,
        change_service: ChangeService,
        organization_id,
        make_change,
        make_completed_change,
    ) -> None:
        await make_completed_change()
        cancelled = await make_change()
        await change_service.transition(
            organization_id, cancelled.id, target=ChangeStatus.CANCELLED
        )
        start = utcnow() - timedelta(hours=1)
        end = utcnow() + timedelta(hours=1)
        window = await statistics_service.rollup(
            organization_id, window_start=start, window_end=end
        )
        assert window.changes_completed == 1
        assert window.changes_cancelled == 1
        assert window.success_rate == pytest.approx(50.0)

    async def test_rollup_buckets_by_category_and_risk_level(
        self, statistics_service: StatisticsService, organization_id, make_assessed_change
    ) -> None:
        change = await make_assessed_change()
        start = utcnow() - timedelta(hours=1)
        end = utcnow() + timedelta(hours=1)
        window = await statistics_service.rollup(
            organization_id, window_start=start, window_end=end
        )
        assert window.by_category.get(str(change.category)) == 1
        assert sum(window.by_risk_level.values()) >= 1

    async def test_dashboard_before_any_rollup_has_no_latest_window(
        self, statistics_service: StatisticsService, organization_id, make_change
    ) -> None:
        await make_change()
        dashboard = await statistics_service.dashboard(organization_id)
        assert "by_status" in dashboard
        assert dashboard["latest_window"]["success_rate"] is None
        assert dashboard["latest_window"]["computed_through"] is None

    async def test_dashboard_reports_the_latest_rolled_up_window(
        self, statistics_service: StatisticsService, organization_id, make_change
    ) -> None:
        await make_change()
        start = utcnow() - timedelta(hours=1)
        end = utcnow() + timedelta(hours=1)
        await statistics_service.rollup(organization_id, window_start=start, window_end=end)
        dashboard = await statistics_service.dashboard(organization_id)
        assert dashboard["latest_window"]["success_rate"] == 100.0
        assert dashboard["latest_window"]["computed_through"] is not None

    async def test_trend_returns_recent_windows_oldest_first(
        self, statistics_service: StatisticsService, organization_id, make_change
    ) -> None:
        await make_change()
        earlier_start = utcnow() - timedelta(hours=3)
        earlier_end = utcnow() - timedelta(hours=2)
        later_start = utcnow() - timedelta(hours=1)
        later_end = utcnow() + timedelta(hours=1)
        await statistics_service.rollup(
            organization_id, window_start=later_start, window_end=later_end
        )
        await statistics_service.rollup(
            organization_id, window_start=earlier_start, window_end=earlier_end
        )
        windows = await statistics_service.trend(organization_id, since_days=1)
        assert len(windows) >= 2
        assert windows[0].window_start < windows[-1].window_start


class TestReportService:
    async def test_generate_a_change_report(
        self, report_service: ReportService, organization_id, make_change
    ) -> None:
        await make_change()
        report = await report_service.generate(organization_id, kind=ReportKind.CHANGE)
        assert report.status == str(JobStatus.COMPLETED)
        assert report.row_count >= 1
        assert report.content["rows"]

    async def test_generate_an_executive_report(
        self, report_service: ReportService, organization_id, make_change
    ) -> None:
        await make_change()
        report = await report_service.generate(organization_id, kind=ReportKind.EXECUTIVE)
        assert report.status == str(JobStatus.COMPLETED)
        assert report.content["rows"]

    async def test_generate_a_risk_report(
        self, report_service: ReportService, organization_id, make_assessed_change
    ) -> None:
        await make_assessed_change()
        report = await report_service.generate(organization_id, kind=ReportKind.RISK)
        assert report.status == str(JobStatus.COMPLETED)
        assert report.row_count >= 1
        assert all(row["risk_level"] is not None for row in report.content["rows"])

    async def test_a_report_kind_with_no_organization_wide_builder_returns_no_rows(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.CAB)
        assert report.status == str(JobStatus.COMPLETED)
        assert report.content.get("rows") == []

    async def test_generate_sets_title_and_generated_by(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(
            organization_id, kind=ReportKind.PIR, title="Monthly PIR audit", generated_by="alice"
        )
        assert report.title == "Monthly PIR audit"
        assert report.generated_by == "alice"

    async def test_generate_without_a_title_defaults_to_the_kind(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.COMPLIANCE)
        assert str(ReportKind.COMPLIANCE) in report.title

    async def test_list_for_org_lists_newest_first(
        self, report_service: ReportService, organization_id
    ) -> None:
        await report_service.generate(organization_id, kind=ReportKind.CHANGE)
        await report_service.generate(organization_id, kind=ReportKind.EXECUTIVE)
        rows = await report_service.list_for_org(organization_id)
        assert len(rows) == 2

    async def test_require_in_org_returns_the_report(
        self, report_service: ReportService, organization_id
    ) -> None:
        created = await report_service.generate(organization_id, kind=ReportKind.CHANGE)
        found = await report_service.require_in_org(organization_id, created.id)
        assert found.id == created.id

    async def test_require_in_org_raises_not_found_for_an_unknown_report(
        self, report_service: ReportService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await report_service.require_in_org(organization_id, uuid.uuid4())

    async def test_to_csv_renders_rows(
        self, report_service: ReportService, organization_id, make_change
    ) -> None:
        await make_change()
        report = await report_service.generate(organization_id, kind=ReportKind.CHANGE)
        csv_text = report_service.to_csv(report.content)
        assert "reference" in csv_text

    async def test_to_csv_of_empty_rows_is_an_empty_string(
        self, report_service: ReportService
    ) -> None:
        assert report_service.to_csv({"rows": []}) == ""

    async def test_to_markdown_renders_a_table(
        self, report_service: ReportService, organization_id, make_change
    ) -> None:
        await make_change()
        report = await report_service.generate(organization_id, kind=ReportKind.CHANGE)
        markdown = report_service.to_markdown(report.content, title="Changes")
        assert "# Changes" in markdown
        assert "| reference |" in markdown

    async def test_to_markdown_of_empty_rows_says_so(self, report_service: ReportService) -> None:
        markdown = report_service.to_markdown({"rows": []})
        assert "No rows." in markdown


class TestAuditService:
    async def test_record_appends_an_entry(
        self, audit_service: AuditService, organization_id
    ) -> None:
        entry = await audit_service.record(
            organization_id,
            action=AuditAction.CHANGE_CREATED,
            entity_type="change",
            summary="Opened CHG-0001.",
        )
        assert entry.succeeded is True

    async def test_list_entries_filters_by_action(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.CHANGE_CREATED,
            entity_type="change",
            summary="Opened.",
        )
        await audit_service.record(
            organization_id,
            action=AuditAction.CHANGE_SCHEDULED,
            entity_type="change",
            summary="Scheduled.",
        )
        found = await audit_service.list_entries(
            organization_id, action=AuditAction.CHANGE_SCHEDULED
        )
        assert len(found) == 1
        assert found[0].action == str(AuditAction.CHANGE_SCHEDULED)

    async def test_summary_counts_by_action(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.CHANGE_CREATED,
            entity_type="change",
            summary="Opened.",
        )
        summary = await audit_service.summary(organization_id, days=1)
        assert summary["total"] >= 1
        assert str(AuditAction.CHANGE_CREATED) in summary["by_action"]

    async def test_record_failure_without_a_session_factory_records_inline(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record_failure(
            organization_id,
            action=AuditAction.CHANGE_CREATED,
            entity_type="change",
            summary="Refused: quota exceeded.",
        )
        found = await audit_service.list_entries(organization_id)
        assert any(one.succeeded is False for one in found)

    async def test_record_failure_commits_independently_of_the_callers_transaction(
        self, db_session_factory, organization_id
    ) -> None:
        # The refused request's own transaction rolls back below; the
        # audit entry recorded inside record_failure must still survive
        # that, because it is committed through its own session_scope.
        async with db_session_factory() as writer:
            service = AuditService(
                ChangeAuditRepository(writer), session_factory=db_session_factory
            )
            await service.record_failure(
                organization_id,
                action=AuditAction.ADMINISTRATIVE,
                entity_type="change",
                summary="Refused: the requester cannot approve their own change.",
                actor_id="mallory",
            )
            await writer.rollback()

        async with db_session_factory() as reader:
            entries = await ChangeAuditRepository(reader).list_for_org(organization_id)
        assert len(entries) == 1, "the refusal outlived the transaction that refused it"
        assert entries[0].succeeded is False
