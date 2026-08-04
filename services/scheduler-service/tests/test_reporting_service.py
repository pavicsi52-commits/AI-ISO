"""StatisticsService, ReportService, AuditService.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared_core.exceptions.not_found import NotFoundError
from tests.conftest import ago, soon

from app.models.enums import AuditAction, JobType, ReportFormat, ReportKind, ReportStatus
from app.repositories.governance import SchedulerAuditRepository
from app.services.reporting import AuditService, ReportService, StatisticsService

pytestmark = pytest.mark.asyncio


class TestRollup:
    async def test_computes_a_fresh_window(
        self, statistics_service: StatisticsService, make_job, organization_id
    ) -> None:
        await make_job()
        window = await statistics_service.rollup(
            organization_id, window_start=ago(1), window_end=soon(1)
        )
        assert window.jobs_scheduled >= 1

    async def test_is_idempotent_by_window_start(
        self, statistics_service: StatisticsService, make_job, organization_id
    ) -> None:
        start, end = ago(1), soon(1)
        first = await statistics_service.rollup(organization_id, window_start=start, window_end=end)
        await make_job()
        second = await statistics_service.rollup(
            organization_id, window_start=start, window_end=end
        )
        assert second.id == first.id

    async def test_zero_terminal_executions_gives_a_hundred_percent_success_rate(
        self, statistics_service: StatisticsService, organization_id
    ) -> None:
        window = await statistics_service.rollup(
            organization_id, window_start=ago(1), window_end=soon(1)
        )
        assert window.success_rate == 100.0

    async def test_counts_jobs_by_type(
        self, statistics_service: StatisticsService, make_job, organization_id
    ) -> None:
        await make_job(job_type=JobType.BACKUP_JOB)
        window = await statistics_service.rollup(
            organization_id, window_start=ago(1), window_end=soon(1)
        )
        assert window.by_job_type.get(str(JobType.BACKUP_JOB), 0) >= 1

    async def test_executions_dispatched_via_execution_service_are_counted(
        self, statistics_service: StatisticsService, execution_service, make_job, organization_id
    ) -> None:
        job = await make_job()
        await execution_service.dispatch(organization_id, job.id, trigger_source="manual")
        window = await statistics_service.rollup(
            organization_id, window_start=ago(1), window_end=soon(1)
        )
        assert window.jobs_completed >= 1
        assert window.success_rate == 100.0


class TestDashboard:
    async def test_returns_a_snapshot_with_no_prior_rollup(
        self, statistics_service: StatisticsService, organization_id
    ) -> None:
        data = await statistics_service.dashboard(organization_id)
        assert data["latest_window"]["computed_through"] is None

    async def test_reflects_a_prior_rollup(
        self, statistics_service: StatisticsService, make_job, organization_id
    ) -> None:
        await make_job()
        await statistics_service.rollup(organization_id, window_start=ago(1), window_end=soon(1))
        data = await statistics_service.dashboard(organization_id)
        assert data["latest_window"]["computed_through"] is not None

    async def test_reflects_jobs_by_status(
        self, statistics_service: StatisticsService, make_job, organization_id
    ) -> None:
        await make_job()
        data = await statistics_service.dashboard(organization_id)
        assert data["jobs_by_status"].get("active", 0) >= 1


class TestTrend:
    async def test_returns_recent_windows_oldest_first(
        self, statistics_service: StatisticsService, make_job, organization_id
    ) -> None:
        await make_job()
        await statistics_service.rollup(organization_id, window_start=ago(2), window_end=ago(1))
        await statistics_service.rollup(organization_id, window_start=ago(1), window_end=soon(1))
        trend = await statistics_service.trend(organization_id, since_days=30)
        assert len(trend) >= 2
        assert trend[0].window_start <= trend[-1].window_start

    async def test_no_windows_returns_an_empty_list(
        self, statistics_service: StatisticsService, organization_id
    ) -> None:
        trend = await statistics_service.trend(organization_id, since_days=30)
        assert trend == []


class TestReportGenerate:
    async def test_execution_report_succeeds(
        self, report_service: ReportService, execution_service, make_job, organization_id
    ) -> None:
        job = await make_job()
        await execution_service.dispatch(organization_id, job.id, trigger_source="manual")
        report = await report_service.generate(organization_id, kind=ReportKind.EXECUTION)
        assert report.status == ReportStatus.COMPLETED
        assert report.row_count is not None
        assert report.row_count >= 1

    async def test_failure_report_succeeds_even_with_no_failures(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.FAILURE)
        assert report.status == ReportStatus.COMPLETED
        assert report.content["rows"] == []

    async def test_performance_report_wraps_the_dashboard_snapshot(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.PERFORMANCE)
        assert report.status == ReportStatus.COMPLETED
        assert len(report.content["rows"]) == 1

    async def test_a_kind_with_no_builder_succeeds_with_empty_rows(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.RETRY)
        assert report.status == ReportStatus.COMPLETED
        assert report.content == {"rows": []}

    async def test_default_title_uses_the_kind(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.EXECUTION)
        assert "execution" in report.title.lower()

    async def test_custom_title_is_respected(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(
            organization_id, kind=ReportKind.EXECUTION, title="My Custom Report"
        )
        assert report.title == "My Custom Report"

    async def test_report_format_is_stored(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(
            organization_id, kind=ReportKind.EXECUTION, report_format=ReportFormat.CSV
        )
        assert report.report_format == ReportFormat.CSV


class TestReportReadAndList:
    async def test_require_in_org_raises_not_found_for_a_missing_report(
        self, report_service: ReportService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await report_service.require_in_org(organization_id, uuid4())

    async def test_require_in_org_is_scoped_to_its_organization(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.EXECUTION)
        with pytest.raises(NotFoundError):
            await report_service.require_in_org(uuid4(), report.id)

    async def test_list_for_org_returns_newest_first(
        self, report_service: ReportService, organization_id
    ) -> None:
        await report_service.generate(organization_id, kind=ReportKind.EXECUTION)
        await report_service.generate(organization_id, kind=ReportKind.FAILURE)
        found = await report_service.list_for_org(organization_id)
        assert len(found) >= 2


class TestReportRendering:
    async def test_to_csv_renders_populated_rows(self) -> None:
        content = {"rows": [{"a": "1", "b": "2"}]}
        rendered = ReportService.to_csv(content)
        assert "a,b" in rendered
        assert "1,2" in rendered

    async def test_to_csv_handles_empty_rows(self) -> None:
        assert ReportService.to_csv({"rows": []}) == ""

    async def test_to_markdown_renders_populated_rows(self) -> None:
        content = {"rows": [{"a": "1", "b": "2"}]}
        rendered = ReportService.to_markdown(content, title="My Report")
        assert "# My Report" in rendered
        assert "| a | b |" in rendered

    async def test_to_markdown_handles_empty_rows(self) -> None:
        rendered = ReportService.to_markdown({"rows": []})
        assert "No rows." in rendered


class TestAuditService:
    async def test_record_appends_an_entry(
        self, audit_service: AuditService, organization_id
    ) -> None:
        entry = await audit_service.record(
            organization_id,
            action=AuditAction.JOB_CREATED,
            entity_type="job",
            summary="Registered a job.",
        )
        assert entry.succeeded is True

    async def test_list_entries_filters_by_action(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id, action=AuditAction.JOB_CREATED, entity_type="job", summary="Created."
        )
        await audit_service.record(
            organization_id, action=AuditAction.JOB_DELETED, entity_type="job", summary="Deleted."
        )
        found = await audit_service.list_entries(organization_id, action=AuditAction.JOB_DELETED)
        assert all(one.action == AuditAction.JOB_DELETED for one in found)

    async def test_list_entries_filters_by_actor(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.JOB_CREATED,
            entity_type="job",
            summary="Created.",
            actor_id="alice",
        )
        found = await audit_service.list_entries(organization_id, actor_id="alice")
        assert all(one.actor_id == "alice" for one in found)

    async def test_summary_counts_by_action(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id, action=AuditAction.JOB_CREATED, entity_type="job", summary="Created."
        )
        summary = await audit_service.summary(organization_id, days=30)
        assert summary["total"] >= 1
        assert str(AuditAction.JOB_CREATED) in summary["by_action"]

    async def test_record_failure_without_a_session_factory_records_inline(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record_failure(
            organization_id,
            action=AuditAction.ADMINISTRATIVE,
            entity_type="job",
            summary="Refused: insufficient permissions.",
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
                SchedulerAuditRepository(writer), session_factory=db_session_factory
            )
            await service.record_failure(
                organization_id,
                action=AuditAction.ADMINISTRATIVE,
                entity_type="job",
                summary="Refused: the requester cannot cancel someone else's job.",
                actor_id="mallory",
            )
            await writer.rollback()

        async with db_session_factory() as reader:
            entries = await SchedulerAuditRepository(reader).list_for_org(organization_id)
        assert len(entries) == 1, "the refusal outlived the transaction that refused it"
        assert entries[0].succeeded is False
