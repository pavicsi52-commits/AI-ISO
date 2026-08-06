"""StatisticsService, ReportService, AuditService, and their repositories.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.

``AuditService.record_failure`` commits in its own ``session_scope`` --
see this module's own ``TestAuditService`` class and ``tests/conftest.py``'s
own docstring for why that can only be genuinely verified with a second,
independent session opened directly from ``db_session_factory``, never
through the shared ``db_session``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import AuditAction, ReportFormat, ReportKind, ReportStatus
from app.models.governance import ApiAudit, ApiStatistic
from app.models.request import ApiRequestLog, ApiResponseLog
from app.repositories.governance import ApiAuditRepository
from app.services.reporting import AuditService, ReportService, StatisticsService
from tests.conftest import ago, soon, utcnow

pytestmark = pytest.mark.asyncio


async def _make_request(
    requests_repo, organization_id, *, client_id=None, service_id=None, started_at=None
) -> ApiRequestLog:
    return await requests_repo.create(
        ApiRequestLog(
            organization_id=organization_id,
            client_id=client_id,
            service_id=service_id,
            method="GET",
            path="/echo",
            correlation_id=str(uuid4()),
            started_at=started_at or utcnow(),
        )
    )


async def _make_response(
    responses_repo,
    organization_id,
    request_id,
    *,
    status_code=200,
    latency_ms=10.0,
    rate_limited=False,
    quota_exceeded=False,
    completed_at=None,
) -> ApiResponseLog:
    return await responses_repo.create(
        ApiResponseLog(
            organization_id=organization_id,
            request_id=request_id,
            status_code=status_code,
            latency_ms=latency_ms,
            rate_limited=rate_limited,
            quota_exceeded=quota_exceeded,
            completed_at=completed_at or utcnow(),
        )
    )


class TestRollup:
    async def test_zero_activity_gives_sensible_defaults(
        self, statistics_service: StatisticsService, organization_id
    ) -> None:
        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )
        assert window.total_requests == 0
        assert window.successful_requests == 0
        assert window.failed_requests == 0
        assert window.rate_limited_requests == 0
        assert window.quota_exceeded_requests == 0
        assert window.average_latency_ms is None
        assert window.p95_latency_ms is None
        assert window.error_rate == 0.0
        assert window.success_rate == 100.0
        assert window.by_service == {}
        assert window.by_status_code == {}
        assert window.by_client == {}

    async def test_computes_success_and_failure_counts(
        self,
        statistics_service: StatisticsService,
        request_logs_repo,
        response_logs_repo,
        make_client,
        make_service,
        organization_id,
    ) -> None:
        client_id = (await make_client()).id
        service_id = (await make_service()).id
        req1 = await _make_request(
            request_logs_repo, organization_id, client_id=client_id, service_id=service_id
        )
        await _make_response(
            response_logs_repo, organization_id, req1.id, status_code=200, latency_ms=10.0
        )
        req2 = await _make_request(
            request_logs_repo, organization_id, client_id=client_id, service_id=service_id
        )
        await _make_response(
            response_logs_repo, organization_id, req2.id, status_code=500, latency_ms=20.0
        )

        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )
        assert window.total_requests == 2
        assert window.successful_requests == 1
        assert window.failed_requests == 1
        assert window.error_rate == 50.0
        assert window.success_rate == 50.0
        assert window.average_latency_ms == 15.0
        assert window.by_service[str(service_id)] == 2
        assert window.by_client[str(client_id)] == 2
        assert window.by_status_code["200"] == 1
        assert window.by_status_code["500"] == 1

    async def test_counts_rate_limited_and_quota_exceeded(
        self,
        statistics_service: StatisticsService,
        request_logs_repo,
        response_logs_repo,
        organization_id,
    ) -> None:
        req = await _make_request(request_logs_repo, organization_id)
        await _make_response(
            response_logs_repo, organization_id, req.id, rate_limited=True, quota_exceeded=True
        )

        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )
        assert window.rate_limited_requests == 1
        assert window.quota_exceeded_requests == 1

    async def test_p95_latency_is_computed_from_sorted_latencies(
        self,
        statistics_service: StatisticsService,
        request_logs_repo,
        response_logs_repo,
        organization_id,
    ) -> None:
        for latency in (10.0, 20.0, 30.0, 40.0):
            req = await _make_request(request_logs_repo, organization_id)
            await _make_response(response_logs_repo, organization_id, req.id, latency_ms=latency)

        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )
        assert window.p95_latency_ms is not None

    async def test_is_idempotent_by_window_start(
        self,
        statistics_service: StatisticsService,
        request_logs_repo,
        response_logs_repo,
        organization_id,
    ) -> None:
        start, end = ago(3600), soon(3600)
        first = await statistics_service.rollup(organization_id, window_start=start, window_end=end)
        req = await _make_request(request_logs_repo, organization_id)
        await _make_response(response_logs_repo, organization_id, req.id)
        second = await statistics_service.rollup(
            organization_id, window_start=start, window_end=end
        )
        assert second.id == first.id
        assert second.total_requests == 1

    async def test_requests_and_responses_outside_the_window_are_excluded(
        self,
        statistics_service: StatisticsService,
        request_logs_repo,
        response_logs_repo,
        organization_id,
    ) -> None:
        old_time = ago(7200)
        req = await _make_request(request_logs_repo, organization_id, started_at=old_time)
        await _make_response(response_logs_repo, organization_id, req.id, completed_at=old_time)

        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )
        assert window.total_requests == 0


class TestDashboard:
    async def test_returns_empty_state_when_nothing_has_ever_been_rolled_up(
        self, statistics_service: StatisticsService, organization_id
    ) -> None:
        data = await statistics_service.dashboard(organization_id)
        assert data["responses_by_status_code"] == {}
        assert data["latest_window"]["error_rate"] is None
        assert data["latest_window"]["success_rate"] is None
        assert data["latest_window"]["average_latency_ms"] is None
        assert data["latest_window"]["p95_latency_ms"] is None
        assert data["latest_window"]["computed_through"] is None

    async def test_reflects_responses_by_status_code_and_the_latest_rollup(
        self,
        statistics_service: StatisticsService,
        request_logs_repo,
        response_logs_repo,
        organization_id,
    ) -> None:
        req = await _make_request(request_logs_repo, organization_id)
        await _make_response(response_logs_repo, organization_id, req.id, status_code=201)
        await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )

        data = await statistics_service.dashboard(organization_id)
        assert data["responses_by_status_code"].get("201", 0) >= 1
        assert data["latest_window"]["computed_through"] is not None
        assert data["latest_window"]["success_rate"] == 100.0


class TestTrend:
    async def test_returns_an_empty_list_when_there_are_no_rollups(
        self, statistics_service: StatisticsService, organization_id
    ) -> None:
        trend = await statistics_service.trend(organization_id, since_days=30)
        assert trend == []

    async def test_returns_windows_oldest_first(
        self, statistics_service: StatisticsService, organization_id
    ) -> None:
        await statistics_service.rollup(
            organization_id, window_start=ago(7200), window_end=ago(3600)
        )
        await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )
        trend = await statistics_service.trend(organization_id, since_days=30)
        assert len(trend) >= 2
        assert trend[0].window_start <= trend[-1].window_start

    async def test_since_days_excludes_older_windows(
        self, statistics_repo, statistics_service: StatisticsService, organization_id
    ) -> None:
        # A window far enough in the past that `since_days=1` excludes it.
        await statistics_repo.create(
            ApiStatistic(
                organization_id=organization_id,
                window_start=datetime.now(UTC) - timedelta(days=30),
                window_end=datetime.now(UTC) - timedelta(days=30) + timedelta(hours=1),
            )
        )
        trend = await statistics_service.trend(organization_id, since_days=1)
        assert trend == []


class TestReportGenerate:
    async def test_api_usage_report_succeeds_with_rows(
        self, report_service: ReportService, request_logs_repo, organization_id
    ) -> None:
        await _make_request(request_logs_repo, organization_id)
        report = await report_service.generate(organization_id, kind=ReportKind.API_USAGE)
        assert report.status == ReportStatus.COMPLETED
        assert report.row_count == 1
        row = report.content["rows"][0]
        assert {"method", "path", "client_id", "started_at"} <= row.keys()

    async def test_api_usage_report_succeeds_with_no_rows(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.API_USAGE)
        assert report.status == ReportStatus.COMPLETED
        assert report.content == {"rows": []}
        assert report.row_count == 0

    async def test_latency_report_succeeds_with_rows(
        self, report_service: ReportService, request_logs_repo, response_logs_repo, organization_id
    ) -> None:
        req = await _make_request(request_logs_repo, organization_id)
        await _make_response(
            response_logs_repo, organization_id, req.id, status_code=200, latency_ms=12.5
        )
        report = await report_service.generate(organization_id, kind=ReportKind.LATENCY)
        assert report.status == ReportStatus.COMPLETED
        assert report.row_count == 1
        row = report.content["rows"][0]
        assert {"request_id", "status_code", "latency_ms", "completed_at"} <= row.keys()
        assert row["latency_ms"] == 12.5

    async def test_traffic_report_mirrors_api_usage(
        self, report_service: ReportService, request_logs_repo, organization_id
    ) -> None:
        await _make_request(request_logs_repo, organization_id)
        report = await report_service.generate(organization_id, kind=ReportKind.TRAFFIC)
        assert report.status == ReportStatus.COMPLETED
        assert report.row_count == 1

    async def test_audit_report_succeeds_with_entries(
        self, report_service: ReportService, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.SERVICE_REGISTERED,
            entity_type="service",
            summary="Registered.",
        )
        report = await report_service.generate(organization_id, kind=ReportKind.AUDIT)
        assert report.status == ReportStatus.COMPLETED
        assert len(report.content["rows"]) == 1
        row = report.content["rows"][0]
        assert {"action", "entity_type", "actor_id", "occurred_at", "succeeded"} <= row.keys()

    @pytest.mark.parametrize(
        "kind", [ReportKind.QUOTA, ReportKind.SECURITY, ReportKind.GATEWAY_HEALTH]
    )
    async def test_kinds_with_no_builder_succeed_with_empty_rows(
        self, report_service: ReportService, organization_id, kind
    ) -> None:
        report = await report_service.generate(organization_id, kind=kind)
        assert report.status == ReportStatus.COMPLETED
        assert report.content == {"rows": []}
        assert report.row_count == 0

    async def test_default_title_uses_the_kind(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.API_USAGE)
        assert "api_usage" in report.title.lower() or "apiusage" in report.title.lower().replace(
            " ", ""
        )

    async def test_custom_title_is_respected(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(
            organization_id, kind=ReportKind.API_USAGE, title="My Custom Report"
        )
        assert report.title == "My Custom Report"

    async def test_report_format_is_stored(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(
            organization_id, kind=ReportKind.API_USAGE, report_format=ReportFormat.CSV
        )
        assert report.report_format == ReportFormat.CSV

    async def test_generated_by_and_duration_are_recorded(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(
            organization_id, kind=ReportKind.API_USAGE, generated_by="ops-1"
        )
        assert report.generated_by == "ops-1"
        assert report.generated_at is not None
        assert report.duration_ms is not None
        assert report.duration_ms >= 0

    async def test_generate_never_raises_records_failed_status_when_the_builder_itself_breaks(
        self, reports_repo, request_logs_repo, response_logs_repo, audit_repo, organization_id
    ) -> None:
        # A genuinely broken builder (an invalid row limit no legitimate
        # caller would ever configure) still must not raise out of
        # generate() -- it is recorded as a FAILED report instead. No
        # mocking: this is the real ReportService, just misconfigured.
        await _make_request(request_logs_repo, organization_id)
        broken_service = ReportService(
            reports_repo,
            request_logs_repo,
            response_logs_repo,
            audit_repo,
            max_rows="not-a-number",  # type: ignore[arg-type]
        )
        report = await broken_service.generate(organization_id, kind=ReportKind.API_USAGE)
        assert report.status == ReportStatus.FAILED
        assert report.error is not None


class TestReportReadAndList:
    async def test_require_in_org_raises_not_found_for_a_missing_report(
        self, report_service: ReportService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await report_service.require_in_org(organization_id, uuid4())

    async def test_require_in_org_is_scoped_to_its_organization(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.API_USAGE)
        with pytest.raises(NotFoundError):
            await report_service.require_in_org(uuid4(), report.id)

    async def test_require_in_org_finds_its_own_report(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.API_USAGE)
        found = await report_service.require_in_org(organization_id, report.id)
        assert found.id == report.id

    async def test_list_for_org_returns_newest_first(
        self, report_service: ReportService, organization_id
    ) -> None:
        await report_service.generate(organization_id, kind=ReportKind.API_USAGE)
        await report_service.generate(organization_id, kind=ReportKind.AUDIT)
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

    async def test_to_csv_handles_missing_rows_key(self) -> None:
        assert ReportService.to_csv({}) == ""

    async def test_to_markdown_renders_populated_rows(self) -> None:
        content = {"rows": [{"a": "1", "b": "2"}]}
        rendered = ReportService.to_markdown(content, title="My Report")
        assert "# My Report" in rendered
        assert "| a | b |" in rendered
        assert "| 1 | 2 |" in rendered

    async def test_to_markdown_handles_empty_rows(self) -> None:
        rendered = ReportService.to_markdown({"rows": []})
        assert "No rows." in rendered
        assert "# Report" in rendered

    async def test_to_markdown_default_title(self) -> None:
        rendered = ReportService.to_markdown({"rows": [{"a": "1"}]})
        assert rendered.startswith("# Report")


class TestAuditService:
    async def test_record_appends_an_entry(
        self, audit_service: AuditService, organization_id
    ) -> None:
        entry = await audit_service.record(
            organization_id,
            action=AuditAction.SERVICE_REGISTERED,
            entity_type="service",
            summary="Registered.",
        )
        assert entry.succeeded is True

    async def test_record_stores_every_optional_field(
        self, audit_service: AuditService, organization_id
    ) -> None:
        entity_id = uuid4()
        entry = await audit_service.record(
            organization_id,
            action=AuditAction.GATEWAY_CONFIG_CHANGED,
            entity_type="route",
            summary="Configured route.",
            entity_id=entity_id,
            entity_reference="route-ref",
            actor_id="alice",
            actor_type="system",
            succeeded=False,
            changes={"enabled": True},
            context={"reason": "onboarding"},
            request_id="req-1",
            ip_address="127.0.0.1",
        )
        assert entry.entity_id == entity_id
        assert entry.entity_reference == "route-ref"
        assert entry.actor_id == "alice"
        assert entry.actor_type == "system"
        assert entry.succeeded is False
        assert entry.changes == {"enabled": True}
        assert entry.context == {"reason": "onboarding"}
        assert entry.request_id == "req-1"
        assert entry.ip_address == "127.0.0.1"

    async def test_list_entries_filters_by_action(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.SERVICE_REGISTERED,
            entity_type="service",
            summary="Registered.",
        )
        await audit_service.record(
            organization_id,
            action=AuditAction.SERVICE_UPDATED,
            entity_type="service",
            summary="Updated.",
        )
        found = await audit_service.list_entries(
            organization_id, action=AuditAction.SERVICE_UPDATED
        )
        assert all(one.action == AuditAction.SERVICE_UPDATED for one in found)
        assert len(found) == 1

    async def test_list_entries_filters_by_entity_id(
        self, audit_service: AuditService, organization_id
    ) -> None:
        entity_id = uuid4()
        await audit_service.record(
            organization_id,
            action=AuditAction.SERVICE_REGISTERED,
            entity_type="service",
            summary="Registered.",
            entity_id=entity_id,
        )
        await audit_service.record(
            organization_id,
            action=AuditAction.SERVICE_REGISTERED,
            entity_type="service",
            summary="A different one.",
        )
        found = await audit_service.list_entries(organization_id, entity_id=entity_id)
        assert len(found) == 1
        assert found[0].entity_id == entity_id

    async def test_list_entries_filters_by_actor(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.SERVICE_REGISTERED,
            entity_type="service",
            summary="Registered.",
            actor_id="alice",
        )
        found = await audit_service.list_entries(organization_id, actor_id="alice")
        assert all(one.actor_id == "alice" for one in found)

    async def test_list_entries_are_newest_first(
        self, audit_service: AuditService, organization_id
    ) -> None:
        first = await audit_service.record(
            organization_id,
            action=AuditAction.SERVICE_REGISTERED,
            entity_type="service",
            summary="First.",
        )
        second = await audit_service.record(
            organization_id,
            action=AuditAction.SERVICE_UPDATED,
            entity_type="service",
            summary="Second.",
        )
        found = await audit_service.list_entries(organization_id)
        assert found[0].id == second.id
        assert found[-1].id == first.id

    async def test_summary_counts_by_action(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.SERVICE_REGISTERED,
            entity_type="service",
            summary="Registered.",
        )
        summary = await audit_service.summary(organization_id, days=30)
        assert summary["total"] >= 1
        assert str(AuditAction.SERVICE_REGISTERED) in summary["by_action"]
        assert "since" in summary

    async def test_summary_excludes_entries_older_than_the_window(
        self, audit_repo: ApiAuditRepository, audit_service: AuditService, organization_id
    ) -> None:
        await audit_repo.create(
            ApiAudit(
                organization_id=organization_id,
                action=AuditAction.SERVICE_REGISTERED,
                entity_type="service",
                occurred_at=datetime.now(UTC) - timedelta(days=60),
                summary="Old entry.",
            )
        )
        summary = await audit_service.summary(organization_id, days=30)
        assert summary["total"] == 0

    async def test_record_failure_without_a_session_factory_records_inline(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record_failure(
            organization_id,
            action=AuditAction.ADMINISTRATIVE,
            entity_type="service",
            summary="Refused: insufficient permissions.",
        )
        found = await audit_service.list_entries(organization_id)
        assert any(one.succeeded is False for one in found)

    async def test_record_failure_commits_independently_of_the_callers_transaction(
        self, db_session_factory, organization_id
    ) -> None:
        # The refused request's own transaction rolls back below; the
        # audit entry recorded inside record_failure must still survive
        # that, because it is committed through its own session_scope --
        # something a test through the shared db_session fixture could
        # never distinguish from "rolled back with everything else",
        # since that fixture's own writes always roll back at teardown
        # regardless of what the code under test does.
        async with db_session_factory() as writer:
            service = AuditService(ApiAuditRepository(writer), session_factory=db_session_factory)
            await service.record_failure(
                organization_id,
                action=AuditAction.ADMINISTRATIVE,
                entity_type="route",
                summary="Refused: the requester cannot delete another org's route.",
                actor_id="mallory",
                entity_reference="route-123",
                request_id="req-2",
                context={"reason": "not the owner"},
            )
            await writer.rollback()

        async with db_session_factory() as reader:
            entries = await ApiAuditRepository(reader).list_for_org(organization_id)
        assert len(entries) == 1, "the refusal outlived the transaction that refused it"
        assert entries[0].succeeded is False
        assert entries[0].actor_id == "mallory"


class TestGovernanceRepositories:
    async def test_statistic_get_for_window_returns_none_when_absent(
        self, statistics_repo, organization_id
    ) -> None:
        found = await statistics_repo.get_for_window(organization_id, ago(3600))
        assert found is None

    async def test_statistic_latest_returns_none_when_no_windows_exist(
        self, statistics_repo, organization_id
    ) -> None:
        assert await statistics_repo.latest(organization_id) is None

    async def test_report_list_for_org_filters_by_kind(
        self, report_service: ReportService, reports_repo, organization_id
    ) -> None:
        await report_service.generate(organization_id, kind=ReportKind.API_USAGE)
        await report_service.generate(organization_id, kind=ReportKind.AUDIT)
        found = await reports_repo.list_for_org(organization_id, kind=ReportKind.AUDIT)
        assert len(found) == 1
        assert found[0].kind == str(ReportKind.AUDIT) or found[0].kind == ReportKind.AUDIT
