"""StatisticsService, ReportService, AuditService, and their repositories.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.

``AuditService.record_failure`` commits in its own ``session_scope`` --
see this module's own ``TestAuditService`` class and ``tests/conftest.py``'s
own docstring for why that can only be genuinely verified with a second,
independent session opened directly from ``db_session_factory``, never
through the shared ``db_session``.

Real delivery attempts (for ``StatisticsService.rollup``) and a real
dead-lettered delivery (for the ``FAILURE``/``RETRY`` report builders) are
produced through the real, fully-wired ``delivery_service`` fixture
against the fake ASGI backend -- not hand-built rows -- the same
"real infra, no mocking" style as every other AI-IOS service's own
reporting test suite.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import AuditAction, ReportFormat, ReportKind, ReportStatus, SubscriptionScope
from app.models.governance import WebhookAudit, WebhookStatistic
from app.repositories.governance import WebhookAuditRepository
from app.services.reporting import AuditService, ReportService, StatisticsService
from tests.conftest import FAKE_BACKEND_URL, ago, soon

pytestmark = pytest.mark.asyncio


async def _make_delivered_attempt(
    delivery_service, make_endpoint, make_subscription, make_event, organization_id
):
    """One real, successfully delivered attempt (status 200) against the fake backend echo route.

    Scoped to its own unique event-type pattern (not `WILDCARD`) so a
    second, unrelated helper call in the same test/organization cannot
    also fan out to *this* endpoint's subscription.
    """
    label = f"ok-{uuid4().hex[:8]}"
    endpoint = await make_endpoint(f"{label}-endpoint", url=f"{FAKE_BACKEND_URL}/echo")
    await make_subscription(
        endpoint.id, scope=SubscriptionScope.EVENT, scope_reference=f"{label}.*"
    )
    event = await make_event(f"{label}.event")
    deliveries = await delivery_service.fan_out(organization_id, event)
    outcome = await delivery_service.deliver(organization_id, deliveries[0])
    return outcome


async def _make_failing_delivery(
    delivery_service,
    make_endpoint,
    make_subscription,
    make_event,
    organization_id,
    *,
    max_attempts=5,
):
    """A real delivery that fails (status 500) against the fake backend error route.

    Scoped to its own unique event-type pattern for the same reason as
    `_make_delivered_attempt` above.
    """
    label = f"fail-{uuid4().hex[:8]}"
    endpoint = await make_endpoint(
        f"{label}-endpoint", url=f"{FAKE_BACKEND_URL}/error", max_attempts=max_attempts
    )
    await make_subscription(
        endpoint.id, scope=SubscriptionScope.EVENT, scope_reference=f"{label}.*"
    )
    event = await make_event(f"{label}.event")
    deliveries = await delivery_service.fan_out(organization_id, event)
    return deliveries[0]


async def _make_dead_letter(
    delivery_service, make_endpoint, make_subscription, make_event, organization_id
):
    """A real dead-lettered delivery: one failing attempt, `max_attempts=1` so it dead-letters."""
    delivery = await _make_failing_delivery(
        delivery_service,
        make_endpoint,
        make_subscription,
        make_event,
        organization_id,
        max_attempts=1,
    )
    outcome = await delivery_service.deliver(organization_id, delivery)
    assert outcome.dead_lettered is True
    return outcome


class TestRollup:
    async def test_zero_activity_gives_sensible_defaults(
        self, statistics_service: StatisticsService, organization_id
    ) -> None:
        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )
        assert window.deliveries_attempted == 0
        assert window.deliveries_succeeded == 0
        assert window.deliveries_failed == 0
        assert window.retries == 0
        assert window.average_latency_ms is None
        assert window.p95_latency_ms is None
        assert window.success_rate == 100.0
        assert window.by_endpoint == {}

    async def test_computes_success_and_failure_counts(
        self,
        statistics_service: StatisticsService,
        delivery_service,
        make_endpoint,
        make_subscription,
        make_event,
        organization_id,
    ) -> None:
        await _make_delivered_attempt(
            delivery_service, make_endpoint, make_subscription, make_event, organization_id
        )
        failing = await _make_failing_delivery(
            delivery_service, make_endpoint, make_subscription, make_event, organization_id
        )
        await delivery_service.deliver(organization_id, failing)

        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )
        assert window.deliveries_attempted == 2
        assert window.deliveries_succeeded == 1
        assert window.deliveries_failed == 1
        assert window.success_rate == 50.0
        assert window.average_latency_ms is not None
        assert window.average_latency_ms >= 0.0

    async def test_counts_retries(
        self,
        statistics_service: StatisticsService,
        delivery_service,
        make_endpoint,
        make_subscription,
        make_event,
        organization_id,
    ) -> None:
        failing = await _make_failing_delivery(
            delivery_service, make_endpoint, make_subscription, make_event, organization_id
        )
        await delivery_service.deliver(organization_id, failing)
        await delivery_service.deliver(organization_id, failing)  # attempt_number=2

        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )
        assert window.deliveries_attempted == 2
        assert window.retries == 1

    async def test_p95_latency_is_computed_from_sorted_latencies(
        self,
        statistics_service: StatisticsService,
        delivery_service,
        make_endpoint,
        make_subscription,
        make_event,
        organization_id,
    ) -> None:
        for _ in range(4):
            await _make_delivered_attempt(
                delivery_service, make_endpoint, make_subscription, make_event, organization_id
            )
        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )
        assert window.p95_latency_ms is not None

    async def test_is_idempotent_by_window_start(
        self,
        statistics_service: StatisticsService,
        delivery_service,
        make_endpoint,
        make_subscription,
        make_event,
        organization_id,
    ) -> None:
        start, end = ago(3600), soon(3600)
        first = await statistics_service.rollup(organization_id, window_start=start, window_end=end)
        await _make_delivered_attempt(
            delivery_service, make_endpoint, make_subscription, make_event, organization_id
        )
        second = await statistics_service.rollup(
            organization_id, window_start=start, window_end=end
        )
        assert second.id == first.id
        assert second.deliveries_attempted == 1

    async def test_attempts_outside_the_window_are_excluded(
        self, statistics_service: StatisticsService, organization_id
    ) -> None:
        window = await statistics_service.rollup(
            organization_id, window_start=ago(7200), window_end=ago(3600)
        )
        assert window.deliveries_attempted == 0

    async def test_by_endpoint_breakdown_is_genuinely_keyed_by_endpoint_id(
        self,
        statistics_service: StatisticsService,
        delivery_service,
        make_endpoint,
        make_subscription,
        make_event,
        organization_id,
    ) -> None:
        # `WebhookDeliveryAttempt.endpoint_id` is denormalized from the
        # parent delivery specifically so this grouping is real (see the
        # column's own docstring) -- two attempts against the same
        # endpoint must collapse into one key, not two.
        endpoint = await make_endpoint()
        await make_subscription(endpoint.id)
        for _ in range(2):
            event = await make_event()
            delivery = await delivery_service.queue_direct(
                organization_id, event, endpoint_id=endpoint.id
            )
            await delivery_service.deliver(organization_id, delivery)

        window = await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )
        assert window.by_endpoint == {str(endpoint.id): 2}
        assert sum(window.by_endpoint.values()) == window.deliveries_attempted


class TestDashboard:
    async def test_returns_empty_state_when_nothing_has_ever_been_rolled_up(
        self, statistics_service: StatisticsService, organization_id
    ) -> None:
        data = await statistics_service.dashboard(organization_id)
        assert data["latest_window"]["deliveries_attempted"] is None
        assert data["latest_window"]["success_rate"] is None
        assert data["latest_window"]["average_latency_ms"] is None
        assert data["latest_window"]["p95_latency_ms"] is None
        assert data["latest_window"]["computed_through"] is None

    async def test_reflects_the_latest_rollup(
        self,
        statistics_service: StatisticsService,
        delivery_service,
        make_endpoint,
        make_subscription,
        make_event,
        organization_id,
    ) -> None:
        await _make_delivered_attempt(
            delivery_service, make_endpoint, make_subscription, make_event, organization_id
        )
        await statistics_service.rollup(
            organization_id, window_start=ago(3600), window_end=soon(3600)
        )

        data = await statistics_service.dashboard(organization_id)
        assert data["latest_window"]["deliveries_attempted"] == 1
        assert data["latest_window"]["success_rate"] == 100.0
        assert data["latest_window"]["computed_through"] is not None


class TestTrend:
    async def test_returns_an_empty_list_when_there_are_no_rollups(
        self, statistics_service: StatisticsService, organization_id
    ) -> None:
        assert await statistics_service.trend(organization_id, since_days=30) == []

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
        assert len(trend) == 2
        assert trend[0].window_start <= trend[-1].window_start

    async def test_since_days_excludes_older_windows(
        self, statistics_repo, statistics_service: StatisticsService, organization_id
    ) -> None:
        await statistics_repo.create(
            WebhookStatistic(
                organization_id=organization_id,
                window_start=datetime.now(UTC) - timedelta(days=30),
                window_end=datetime.now(UTC) - timedelta(days=30) + timedelta(hours=1),
            )
        )
        trend = await statistics_service.trend(organization_id, since_days=1)
        assert trend == []


class TestReportGenerate:
    async def test_delivery_report_succeeds_with_rows(
        self, report_service: ReportService, make_event, organization_id
    ) -> None:
        await make_event("order.created")
        report = await report_service.generate(organization_id, kind=ReportKind.DELIVERY)
        assert report.status == ReportStatus.COMPLETED
        assert report.row_count == 1
        row = report.content["rows"][0]
        assert {"event_type", "kind", "created_at"} <= row.keys()
        assert row["event_type"] == "order.created"

    async def test_delivery_report_succeeds_with_no_rows(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.DELIVERY)
        assert report.status == ReportStatus.COMPLETED
        assert report.content == {"rows": []}
        assert report.row_count == 0

    async def test_failure_report_succeeds_with_no_dead_letters(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.FAILURE)
        assert report.status == ReportStatus.COMPLETED
        assert report.content["rows"] == []

    async def test_failure_report_succeeds_with_a_dead_letter(
        self,
        report_service: ReportService,
        delivery_service,
        make_endpoint,
        make_subscription,
        make_event,
        organization_id,
    ) -> None:
        await _make_dead_letter(
            delivery_service, make_endpoint, make_subscription, make_event, organization_id
        )
        report = await report_service.generate(organization_id, kind=ReportKind.FAILURE)
        assert report.status == ReportStatus.COMPLETED
        assert len(report.content["rows"]) == 1
        row = report.content["rows"][0]
        assert {
            "delivery_id",
            "endpoint_id",
            "attempt_count",
            "last_error",
            "dead_lettered_at",
        } <= row.keys()

    async def test_retry_report_mirrors_the_failure_report(
        self,
        report_service: ReportService,
        delivery_service,
        make_endpoint,
        make_subscription,
        make_event,
        organization_id,
    ) -> None:
        await _make_dead_letter(
            delivery_service, make_endpoint, make_subscription, make_event, organization_id
        )
        report = await report_service.generate(organization_id, kind=ReportKind.RETRY)
        assert report.status == ReportStatus.COMPLETED
        assert len(report.content["rows"]) == 1

    async def test_audit_report_succeeds_with_entries(
        self, report_service: ReportService, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.ADMINISTRATIVE,
            entity_type="endpoint",
            summary="Registered.",
        )
        report = await report_service.generate(organization_id, kind=ReportKind.AUDIT)
        assert report.status == ReportStatus.COMPLETED
        assert len(report.content["rows"]) == 1
        row = report.content["rows"][0]
        assert {"action", "entity_type", "actor_id", "occurred_at", "succeeded"} <= row.keys()

    @pytest.mark.parametrize("kind", [ReportKind.ENDPOINT, ReportKind.REPLAY, ReportKind.SECURITY])
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
        report = await report_service.generate(organization_id, kind=ReportKind.DELIVERY)
        assert "delivery" in report.title.lower()

    async def test_custom_title_is_respected(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(
            organization_id, kind=ReportKind.DELIVERY, title="My Custom Report"
        )
        assert report.title == "My Custom Report"

    async def test_report_format_is_stored(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(
            organization_id, kind=ReportKind.DELIVERY, report_format=ReportFormat.CSV
        )
        assert report.report_format == ReportFormat.CSV

    async def test_generated_by_and_duration_are_recorded(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(
            organization_id, kind=ReportKind.DELIVERY, generated_by="ops-1"
        )
        assert report.generated_by == "ops-1"
        assert report.generated_at is not None
        assert report.duration_ms is not None
        assert report.duration_ms >= 0

    async def test_generate_never_raises_records_failed_status_when_the_builder_itself_breaks(
        self,
        reports_repo,
        attempts_repo,
        events_repo,
        dead_letters_repo,
        audit_repo,
        make_event,
        organization_id,
    ) -> None:
        # A genuinely broken builder (an invalid row limit no legitimate
        # caller would ever configure) still must not raise out of
        # generate() -- it is recorded as a FAILED report instead. No
        # mocking: this is the real ReportService, just misconfigured.
        await make_event()
        broken_service = ReportService(
            reports_repo,
            attempts_repo,
            events_repo,
            dead_letters_repo,
            audit_repo,
            max_rows="not-a-number",  # type: ignore[arg-type]
        )
        report = await broken_service.generate(organization_id, kind=ReportKind.DELIVERY)
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
        report = await report_service.generate(organization_id, kind=ReportKind.DELIVERY)
        with pytest.raises(NotFoundError):
            await report_service.require_in_org(uuid4(), report.id)

    async def test_require_in_org_finds_its_own_report(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.DELIVERY)
        found = await report_service.require_in_org(organization_id, report.id)
        assert found.id == report.id

    async def test_list_for_org_returns_newest_first(
        self, report_service: ReportService, organization_id
    ) -> None:
        first = await report_service.generate(organization_id, kind=ReportKind.DELIVERY)
        second = await report_service.generate(organization_id, kind=ReportKind.AUDIT)
        found = await report_service.list_for_org(organization_id)
        assert found[0].id == second.id
        assert found[-1].id == first.id

    async def test_list_for_org_respects_limit_and_offset(
        self, report_service: ReportService, organization_id
    ) -> None:
        for _ in range(3):
            await report_service.generate(organization_id, kind=ReportKind.DELIVERY)
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


class TestAuditService:
    async def test_record_appends_an_entry(
        self, audit_service: AuditService, organization_id
    ) -> None:
        entry = await audit_service.record(
            organization_id,
            action=AuditAction.ADMINISTRATIVE,
            entity_type="endpoint",
            summary="Registered.",
        )
        assert entry.succeeded is True

    async def test_record_stores_every_optional_field(
        self, audit_service: AuditService, organization_id
    ) -> None:
        entity_id = uuid4()
        entry = await audit_service.record(
            organization_id,
            action=AuditAction.SECRET_ROTATED,
            entity_type="signature",
            summary="Rotated secret.",
            entity_id=entity_id,
            entity_reference="sig-ref",
            actor_id="alice",
            actor_type="system",
            succeeded=False,
            changes={"rotated": True},
            context={"reason": "scheduled"},
            request_id="req-1",
            ip_address="127.0.0.1",
        )
        assert entry.entity_id == entity_id
        assert entry.entity_reference == "sig-ref"
        assert entry.actor_id == "alice"
        assert entry.actor_type == "system"
        assert entry.succeeded is False
        assert entry.changes == {"rotated": True}
        assert entry.context == {"reason": "scheduled"}
        assert entry.request_id == "req-1"
        assert entry.ip_address == "127.0.0.1"

    async def test_list_entries_filters_by_action(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.ENDPOINT_REGISTERED,
            entity_type="endpoint",
            summary="Registered.",
        )
        await audit_service.record(
            organization_id,
            action=AuditAction.ENDPOINT_UPDATED,
            entity_type="endpoint",
            summary="Updated.",
        )
        found = await audit_service.list_entries(
            organization_id, action=AuditAction.ENDPOINT_UPDATED
        )
        assert all(one.action == AuditAction.ENDPOINT_UPDATED for one in found)
        assert len(found) == 1

    async def test_list_entries_filters_by_entity_id(
        self, audit_service: AuditService, organization_id
    ) -> None:
        entity_id = uuid4()
        await audit_service.record(
            organization_id,
            action=AuditAction.ENDPOINT_REGISTERED,
            entity_type="endpoint",
            summary="Registered.",
            entity_id=entity_id,
        )
        await audit_service.record(
            organization_id,
            action=AuditAction.ENDPOINT_REGISTERED,
            entity_type="endpoint",
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
            action=AuditAction.ENDPOINT_REGISTERED,
            entity_type="endpoint",
            summary="First.",
        )
        second = await audit_service.record(
            organization_id,
            action=AuditAction.ENDPOINT_UPDATED,
            entity_type="endpoint",
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
                entity_type="endpoint",
                summary="One.",
            )
        found = await audit_service.list_entries(organization_id, limit=1, offset=1)
        assert len(found) == 1

    async def test_summary_counts_by_action(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.ENDPOINT_REGISTERED,
            entity_type="endpoint",
            summary="Registered.",
        )
        summary = await audit_service.summary(organization_id, days=30)
        assert summary["total"] >= 1
        assert str(AuditAction.ENDPOINT_REGISTERED) in summary["by_action"]
        assert "since" in summary

    async def test_summary_excludes_entries_older_than_the_window(
        self, audit_repo: WebhookAuditRepository, audit_service: AuditService, organization_id
    ) -> None:
        await audit_repo.create(
            WebhookAudit(
                organization_id=organization_id,
                action=AuditAction.ENDPOINT_REGISTERED,
                entity_type="endpoint",
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
            entity_type="endpoint",
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
                WebhookAuditRepository(writer), session_factory=db_session_factory
            )
            await service.record_failure(
                organization_id,
                action=AuditAction.ADMINISTRATIVE,
                entity_type="endpoint",
                summary="Refused: the requester cannot delete another org's endpoint.",
                actor_id="mallory",
                entity_reference="endpoint-123",
                request_id="req-2",
                context={"reason": "not the owner"},
            )
            await writer.rollback()

        async with db_session_factory() as reader:
            entries = await WebhookAuditRepository(reader).list_for_org(organization_id)
        assert len(entries) == 1, "the refusal outlived the transaction that refused it"
        assert entries[0].succeeded is False
        assert entries[0].actor_id == "mallory"


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
        report = await report_service.generate(organization_id, kind=ReportKind.DELIVERY)
        with pytest.raises(NotFoundError):
            await reports_repo.require_in_org(uuid4(), report.id)

    async def test_audit_count_by_action_groups_correctly(
        self, audit_repo: WebhookAuditRepository, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.ENDPOINT_REGISTERED,
            entity_type="endpoint",
            summary="One.",
        )
        await audit_service.record(
            organization_id,
            action=AuditAction.ENDPOINT_REGISTERED,
            entity_type="endpoint",
            summary="Two.",
        )
        await audit_service.record(
            organization_id,
            action=AuditAction.ENDPOINT_UPDATED,
            entity_type="endpoint",
            summary="Three.",
        )
        counts = await audit_repo.count_by_action(organization_id, since=ago(3600))
        assert counts[str(AuditAction.ENDPOINT_REGISTERED)] == 2
        assert counts[str(AuditAction.ENDPOINT_UPDATED)] == 1
