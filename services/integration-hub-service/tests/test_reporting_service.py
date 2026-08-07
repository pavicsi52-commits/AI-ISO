"""StatisticsService, ReportService, AuditService, and their repositories.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.

``AuditService.record_failure`` commits in its own ``session_scope`` --
see this module's own ``TestRecordFailure`` class and ``tests/conftest.py``'s
own docstring for why that can only be genuinely verified with a second,
independent session opened directly from ``db_session_factory``, never
through the shared ``db_session``.

Real ``ConnectorSyncJob``/``ConnectorHealth``/``ConnectorAudit`` rows (for
``StatisticsService.rollup`` and the ``ReportService`` builders) are
written directly through their own repositories, scoped to a real
``Connector`` created through ``make_connector`` -- ``connector_id`` is a
genuine foreign key to ``connectors.id``, so a sync job or health check
cannot be attached to a connector that does not exist.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import AuditAction, ReportFormat, ReportKind, ReportStatus, SyncStatus
from app.models.governance import ConnectorAudit, ConnectorStatistic
from app.models.sync import ConnectorSyncJob
from app.repositories.governance import ConnectorAuditRepository
from app.services.reporting import AuditService, ReportService, StatisticsService
from tests.conftest import ago, soon


async def _make_sync_job(
    sync_jobs_repo,
    organization_id,
    connector_id,
    *,
    status: SyncStatus = SyncStatus.COMPLETED,
    records_processed: int = 0,
    records_failed: int = 0,
    created_at: datetime | None = None,
) -> ConnectorSyncJob:
    """One real ``connector_sync_jobs`` row, written directly (not through ``SyncService``)
    so its ``created_at`` can be pinned to a specific rollup window."""
    return await sync_jobs_repo.create(
        ConnectorSyncJob(
            organization_id=organization_id,
            connector_id=connector_id,
            status=status,
            records_processed=records_processed,
            records_failed=records_failed,
            created_at=created_at or datetime.now(UTC),
        )
    )


class TestRollup:
    async def test_zero_activity_gives_sensible_defaults(
        self, statistics_service: StatisticsService, organization_id
    ) -> None:
        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )
        assert window.syncs_attempted == 0
        assert window.syncs_succeeded == 0
        assert window.syncs_failed == 0
        assert window.records_processed == 0
        assert window.success_rate == 100.0
        assert window.by_connector == {}

    async def test_computes_success_and_failure_counts(
        self, statistics_service: StatisticsService, sync_jobs_repo, make_connector, organization_id
    ) -> None:
        connector = await make_connector("stat-connector")
        await _make_sync_job(
            sync_jobs_repo,
            organization_id,
            connector.id,
            status=SyncStatus.COMPLETED,
            records_processed=10,
        )
        await _make_sync_job(
            sync_jobs_repo,
            organization_id,
            connector.id,
            status=SyncStatus.COMPLETED,
            records_processed=5,
        )
        await _make_sync_job(
            sync_jobs_repo,
            organization_id,
            connector.id,
            status=SyncStatus.FAILED,
            records_processed=2,
        )
        await _make_sync_job(
            sync_jobs_repo, organization_id, connector.id, status=SyncStatus.PENDING
        )

        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )
        assert window.syncs_attempted == 4
        assert window.syncs_succeeded == 2
        assert window.syncs_failed == 1
        assert window.records_processed == 17
        assert window.success_rate == 50.0

    async def test_attempts_outside_the_window_are_excluded(
        self, statistics_service: StatisticsService, sync_jobs_repo, make_connector, organization_id
    ) -> None:
        connector = await make_connector()
        await _make_sync_job(
            sync_jobs_repo,
            organization_id,
            connector.id,
            status=SyncStatus.COMPLETED,
            created_at=ago(7200),
        )

        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )
        assert window.syncs_attempted == 0

    async def test_is_idempotent_by_window_start(
        self, statistics_service: StatisticsService, sync_jobs_repo, make_connector, organization_id
    ) -> None:
        connector = await make_connector()
        start, end = ago(3600), soon(3600)
        first = await statistics_service.rollup(organization_id, window_start=start, window_end=end)
        await _make_sync_job(
            sync_jobs_repo, organization_id, connector.id, status=SyncStatus.COMPLETED
        )
        second = await statistics_service.rollup(organization_id, window_start=start, window_end=end)

        assert second.id == first.id
        assert second.syncs_attempted == 1

    async def test_by_connector_breakdown_is_genuinely_keyed_by_connector_id(
        self, statistics_service: StatisticsService, sync_jobs_repo, make_connector, organization_id
    ) -> None:
        # Regression guard for the exact bug class that hit webhook-service's
        # own `by_endpoint` breakdown twice already: two sync jobs against
        # the SAME connector must collapse into one key with count 2, not
        # split into two separate keys (e.g. keyed by the job's own id, or
        # by organization_id, instead of by connector_id).
        connector = await make_connector("primary-connector")
        for _ in range(2):
            await _make_sync_job(
                sync_jobs_repo, organization_id, connector.id, status=SyncStatus.COMPLETED
            )

        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )
        assert window.by_connector == {str(connector.id): 2}
        assert sum(window.by_connector.values()) == window.syncs_attempted

    async def test_by_connector_breakdown_splits_correctly_across_multiple_connectors(
        self, statistics_service: StatisticsService, sync_jobs_repo, make_connector, organization_id
    ) -> None:
        first = await make_connector("connector-one")
        second = await make_connector("connector-two")
        for _ in range(2):
            await _make_sync_job(
                sync_jobs_repo, organization_id, first.id, status=SyncStatus.COMPLETED
            )
        await _make_sync_job(sync_jobs_repo, organization_id, second.id, status=SyncStatus.FAILED)

        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )
        assert window.by_connector == {str(first.id): 2, str(second.id): 1}


class TestDashboard:
    async def test_returns_empty_state_when_nothing_has_ever_been_rolled_up(
        self, statistics_service: StatisticsService, organization_id
    ) -> None:
        data = await statistics_service.dashboard(organization_id)
        latest = data["latest_window"]
        assert latest["syncs_attempted"] is None
        assert latest["success_rate"] is None
        assert latest["records_processed"] is None
        assert latest["computed_through"] is None

    async def test_reflects_the_latest_rollup(
        self, statistics_service: StatisticsService, sync_jobs_repo, make_connector, organization_id
    ) -> None:
        connector = await make_connector()
        await _make_sync_job(
            sync_jobs_repo,
            organization_id,
            connector.id,
            status=SyncStatus.COMPLETED,
            records_processed=3,
        )
        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )

        data = await statistics_service.dashboard(organization_id)
        latest = data["latest_window"]
        assert latest["syncs_attempted"] == 1
        assert latest["success_rate"] == 100.0
        assert latest["records_processed"] == 3
        assert latest["computed_through"] == window.window_end.isoformat()


class TestTrend:
    async def test_returns_an_empty_list_when_there_are_no_rollups(
        self, statistics_service: StatisticsService, organization_id
    ) -> None:
        assert await statistics_service.trend(organization_id, since_days=30) == []

    async def test_returns_windows_oldest_first(
        self, statistics_service: StatisticsService, organization_id
    ) -> None:
        older = await statistics_service.rollup(
            organization_id, window_start=ago(7200), window_end=ago(3600)
        )
        newer = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )
        trend = await statistics_service.trend(organization_id, since_days=30)
        assert [row.id for row in trend] == [older.id, newer.id]

    async def test_since_days_excludes_older_windows(
        self, statistics_repo, statistics_service: StatisticsService, organization_id
    ) -> None:
        old_start = datetime.now(UTC) - timedelta(days=30)
        await statistics_repo.create(
            ConnectorStatistic(
                organization_id=organization_id,
                window_start=old_start,
                window_end=old_start + timedelta(hours=1),
            )
        )
        trend = await statistics_service.trend(organization_id, since_days=1)
        assert trend == []


class TestReportGenerateConnector:
    async def test_succeeds_with_rows(
        self, report_service: ReportService, make_connector, organization_id
    ) -> None:
        await make_connector("report-connector", category="custom")
        report = await report_service.generate(organization_id, kind=ReportKind.CONNECTOR)
        assert report.status == ReportStatus.COMPLETED
        assert report.row_count == 1
        row = report.content["rows"][0]
        assert {"name", "category", "status", "enabled"} <= row.keys()
        assert row["name"] == "report-connector"

    async def test_succeeds_with_no_rows(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.CONNECTOR)
        assert report.status == ReportStatus.COMPLETED
        assert report.content == {"rows": []}
        assert report.row_count == 0


class TestReportGenerateSynchronization:
    async def test_succeeds_with_rows(
        self,
        report_service: ReportService,
        sync_jobs_repo,
        make_connector,
        organization_id,
    ) -> None:
        connector = await make_connector()
        await _make_sync_job(
            sync_jobs_repo,
            organization_id,
            connector.id,
            status=SyncStatus.COMPLETED,
            records_processed=4,
            records_failed=1,
        )
        report = await report_service.generate(organization_id, kind=ReportKind.SYNCHRONIZATION)
        assert report.status == ReportStatus.COMPLETED
        assert report.row_count == 1
        row = report.content["rows"][0]
        assert {"connector_id", "status", "records_processed", "records_failed", "created_at"} <= (
            row.keys()
        )
        assert row["connector_id"] == str(connector.id)
        assert row["records_processed"] == 4
        assert row["records_failed"] == 1

    async def test_succeeds_with_no_rows(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.SYNCHRONIZATION)
        assert report.status == ReportStatus.COMPLETED
        assert report.content == {"rows": []}


class TestReportGenerateHealth:
    async def test_only_includes_connectors_with_a_recorded_health_check(
        self,
        report_service: ReportService,
        health_service,
        make_connector,
        organization_id,
    ) -> None:
        probed = await make_connector("probed-connector")
        await make_connector("unprobed-connector")
        await health_service.probe(probed)

        report = await report_service.generate(organization_id, kind=ReportKind.HEALTH)
        assert report.status == ReportStatus.COMPLETED
        assert report.row_count == 1
        row = report.content["rows"][0]
        assert {"connector_id", "status", "checked_at"} <= row.keys()
        assert row["connector_id"] == str(probed.id)

    async def test_succeeds_with_no_rows_when_nothing_has_ever_been_probed(
        self, report_service: ReportService, make_connector, organization_id
    ) -> None:
        await make_connector()
        report = await report_service.generate(organization_id, kind=ReportKind.HEALTH)
        assert report.status == ReportStatus.COMPLETED
        assert report.content == {"rows": []}


class TestReportGenerateAudit:
    async def test_succeeds_with_entries(
        self, report_service: ReportService, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.CONNECTOR_REGISTERED,
            entity_type="connector",
            summary="Registered.",
        )
        report = await report_service.generate(organization_id, kind=ReportKind.AUDIT)
        assert report.status == ReportStatus.COMPLETED
        assert report.row_count == 1
        row = report.content["rows"][0]
        assert {"action", "entity_type", "actor_id", "occurred_at", "succeeded"} <= row.keys()
        assert row["action"] == str(AuditAction.CONNECTOR_REGISTERED)

    async def test_succeeds_with_no_rows(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.AUDIT)
        assert report.status == ReportStatus.COMPLETED
        assert report.content == {"rows": []}


class TestReportGenerateKindsWithNoBuilder:
    @pytest.mark.parametrize(
        "kind", [ReportKind.CREDENTIAL, ReportKind.MARKETPLACE, ReportKind.PERFORMANCE]
    )
    async def test_succeed_with_empty_rows(
        self, report_service: ReportService, organization_id, kind: ReportKind
    ) -> None:
        report = await report_service.generate(organization_id, kind=kind)
        assert report.status == ReportStatus.COMPLETED
        assert report.content == {"rows": []}
        assert report.row_count == 0


class TestReportGenerateMisc:
    async def test_default_title_uses_the_kind(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.CONNECTOR)
        assert "connector" in report.title.lower()

    async def test_custom_title_is_respected(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(
            organization_id, kind=ReportKind.CONNECTOR, title="My Custom Report"
        )
        assert report.title == "My Custom Report"

    async def test_report_format_is_stored(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(
            organization_id, kind=ReportKind.CONNECTOR, report_format=ReportFormat.CSV
        )
        assert report.report_format == ReportFormat.CSV

    async def test_generated_by_and_duration_are_recorded(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(
            organization_id, kind=ReportKind.CONNECTOR, generated_by="ops-1"
        )
        assert report.generated_by == "ops-1"
        assert report.generated_at is not None
        assert report.duration_ms is not None
        assert report.duration_ms >= 0

    async def test_generate_never_raises_records_failed_status_when_the_builder_itself_breaks(
        self,
        reports_repo,
        connectors_repo,
        sync_jobs_repo,
        health_repo,
        audit_repo,
        make_connector,
        organization_id,
    ) -> None:
        # A genuinely broken builder (an invalid row limit no legitimate
        # caller would ever configure) still must not raise out of
        # generate() -- it is recorded as a FAILED report instead. No
        # mocking: this is the real ReportService, just misconfigured.
        await make_connector()
        broken_service = ReportService(
            reports_repo,
            connectors_repo,
            sync_jobs_repo,
            health_repo,
            audit_repo,
            max_rows="not-a-number",  # type: ignore[arg-type]
        )
        report = await broken_service.generate(organization_id, kind=ReportKind.CONNECTOR)
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
        report = await report_service.generate(organization_id, kind=ReportKind.CONNECTOR)
        with pytest.raises(NotFoundError):
            await report_service.require_in_org(uuid4(), report.id)

    async def test_require_in_org_finds_its_own_report(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.CONNECTOR)
        found = await report_service.require_in_org(organization_id, report.id)
        assert found.id == report.id

    async def test_list_for_org_returns_newest_first(
        self, report_service: ReportService, organization_id
    ) -> None:
        first = await report_service.generate(organization_id, kind=ReportKind.CONNECTOR)
        second = await report_service.generate(organization_id, kind=ReportKind.AUDIT)
        found = await report_service.list_for_org(organization_id)
        assert found[0].id == second.id
        assert found[-1].id == first.id

    async def test_list_for_org_respects_limit_and_offset(
        self, report_service: ReportService, organization_id
    ) -> None:
        for _ in range(3):
            await report_service.generate(organization_id, kind=ReportKind.CONNECTOR)
        found = await report_service.list_for_org(organization_id, limit=1, offset=1)
        assert len(found) == 1


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


class TestAuditServiceRecord:
    async def test_record_appends_an_entry(
        self, audit_service: AuditService, organization_id
    ) -> None:
        entry = await audit_service.record(
            organization_id,
            action=AuditAction.ADMINISTRATIVE,
            entity_type="connector",
            summary="Registered.",
        )
        assert entry.succeeded is True

    async def test_record_stores_every_optional_field(
        self, audit_service: AuditService, organization_id
    ) -> None:
        entity_id = uuid4()
        entry = await audit_service.record(
            organization_id,
            action=AuditAction.CREDENTIAL_ROTATED,
            entity_type="credential",
            summary="Rotated secret.",
            entity_id=entity_id,
            entity_reference="cred-ref",
            actor_id="alice",
            actor_type="system",
            succeeded=False,
            changes={"rotated": True},
            context={"reason": "scheduled"},
            request_id="req-1",
            ip_address="127.0.0.1",
        )
        assert entry.entity_id == entity_id
        assert entry.entity_reference == "cred-ref"
        assert entry.actor_id == "alice"
        assert entry.actor_type == "system"
        assert entry.succeeded is False
        assert entry.changes == {"rotated": True}
        assert entry.context == {"reason": "scheduled"}
        assert entry.request_id == "req-1"
        assert entry.ip_address == "127.0.0.1"


class TestAuditServiceListAndSummary:
    async def test_list_entries_filters_by_action(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.CONNECTOR_REGISTERED,
            entity_type="connector",
            summary="Registered.",
        )
        await audit_service.record(
            organization_id,
            action=AuditAction.CONNECTOR_ENABLED,
            entity_type="connector",
            summary="Enabled.",
        )
        found = await audit_service.list_entries(
            organization_id, action=AuditAction.CONNECTOR_ENABLED
        )
        assert all(one.action == AuditAction.CONNECTOR_ENABLED for one in found)
        assert len(found) == 1

    async def test_list_entries_filters_by_entity_id(
        self, audit_service: AuditService, organization_id
    ) -> None:
        entity_id = uuid4()
        await audit_service.record(
            organization_id,
            action=AuditAction.CONNECTOR_REGISTERED,
            entity_type="connector",
            summary="Registered.",
            entity_id=entity_id,
        )
        await audit_service.record(
            organization_id,
            action=AuditAction.CONNECTOR_REGISTERED,
            entity_type="connector",
            summary="A different one.",
        )
        found = await audit_service.list_entries(organization_id, entity_id=entity_id)
        assert len(found) == 1
        assert found[0].entity_id == entity_id

    async def test_list_entries_are_newest_first(
        self, audit_service: AuditService, organization_id
    ) -> None:
        first = await audit_service.record(
            organization_id,
            action=AuditAction.CONNECTOR_REGISTERED,
            entity_type="connector",
            summary="First.",
        )
        second = await audit_service.record(
            organization_id,
            action=AuditAction.CONNECTOR_ENABLED,
            entity_type="connector",
            summary="Second.",
        )
        found = await audit_service.list_entries(organization_id)
        assert found[0].id == second.id
        assert found[-1].id == first.id

    async def test_list_entries_respects_limit_and_offset(
        self, audit_service: AuditService, organization_id
    ) -> None:
        for _ in range(3):
            await audit_service.record(
                organization_id,
                action=AuditAction.ADMINISTRATIVE,
                entity_type="connector",
                summary="One.",
            )
        found = await audit_service.list_entries(organization_id, limit=1, offset=1)
        assert len(found) == 1

    async def test_list_entries_is_tenant_scoped(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.ADMINISTRATIVE,
            entity_type="connector",
            summary="In this org.",
        )
        found = await audit_service.list_entries(uuid4())
        assert found == []

    async def test_summary_counts_by_action(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.CONNECTOR_REGISTERED,
            entity_type="connector",
            summary="Registered.",
        )
        summary = await audit_service.summary(organization_id, days=30)
        assert summary["total"] >= 1
        assert str(AuditAction.CONNECTOR_REGISTERED) in summary["by_action"]
        assert "since" in summary

    async def test_summary_excludes_entries_older_than_the_window(
        self, audit_repo: ConnectorAuditRepository, organization_id
    ) -> None:
        await audit_repo.create(
            ConnectorAudit(
                organization_id=organization_id,
                action=AuditAction.CONNECTOR_REGISTERED,
                entity_type="connector",
                occurred_at=datetime.now(UTC) - timedelta(days=60),
                summary="Old entry.",
            )
        )
        summary = await AuditService(audit_repo).summary(organization_id, days=30)
        assert summary["total"] == 0


class TestRecordFailure:
    async def test_record_failure_without_a_session_factory_records_inline(
        self, audit_service: AuditService, organization_id
    ) -> None:
        # The `audit_service` fixture builds `AuditService` with no
        # `session_factory` -- the fallback branch that just calls
        # `record()` on the request session, exercised here directly.
        await audit_service.record_failure(
            organization_id,
            action=AuditAction.ADMINISTRATIVE,
            entity_type="connector",
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
            service = AuditService(
                ConnectorAuditRepository(writer), session_factory=db_session_factory
            )
            await service.record_failure(
                organization_id,
                action=AuditAction.ADMINISTRATIVE,
                entity_type="connector",
                summary="Refused: the requester cannot remove another org's connector.",
                actor_id="mallory",
                entity_reference="connector-123",
                request_id="req-2",
                context={"reason": "not the owner"},
            )
            await writer.rollback()

        async with db_session_factory() as reader:
            entries = await ConnectorAuditRepository(reader).list_for_org(organization_id)
        assert len(entries) == 1, "the refusal outlived the transaction that refused it"
        assert entries[0].succeeded is False
        assert entries[0].actor_id == "mallory"
        assert entries[0].entity_reference == "connector-123"
        assert entries[0].request_id == "req-2"
        assert entries[0].context == {"reason": "not the owner"}

    async def test_record_failure_with_a_session_factory_is_still_visible_without_a_rollback(
        self, db_session_factory, organization_id
    ) -> None:
        async with db_session_factory() as writer:
            service = AuditService(
                ConnectorAuditRepository(writer), session_factory=db_session_factory
            )
            await service.record_failure(
                organization_id,
                action=AuditAction.ADMINISTRATIVE,
                entity_type="connector",
                summary="Refused.",
            )

        async with db_session_factory() as reader:
            entries = await ConnectorAuditRepository(reader).list_for_org(organization_id)
        assert len(entries) == 1


class TestGovernanceRepositories:
    async def test_statistic_get_for_window_returns_none_when_absent(
        self, statistics_repo, organization_id
    ) -> None:
        assert await statistics_repo.get_for_window(organization_id, ago(3600)) is None

    async def test_statistic_latest_returns_none_when_no_windows_exist(
        self, statistics_repo, organization_id
    ) -> None:
        assert await statistics_repo.latest(organization_id) is None

    async def test_report_require_in_org_is_scoped_to_its_organization(
        self, reports_repo, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.CONNECTOR)
        with pytest.raises(NotFoundError):
            await reports_repo.require_in_org(uuid4(), report.id)

    async def test_audit_count_by_action_groups_correctly(
        self, audit_repo: ConnectorAuditRepository, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.CONNECTOR_REGISTERED,
            entity_type="connector",
            summary="One.",
        )
        await audit_service.record(
            organization_id,
            action=AuditAction.CONNECTOR_REGISTERED,
            entity_type="connector",
            summary="Two.",
        )
        await audit_service.record(
            organization_id,
            action=AuditAction.CONNECTOR_ENABLED,
            entity_type="connector",
            summary="Three.",
        )
        counts = await audit_repo.count_by_action(organization_id, since=ago(3600))
        assert counts[str(AuditAction.CONNECTOR_REGISTERED)] == 2
        assert counts[str(AuditAction.CONNECTOR_ENABLED)] == 1
