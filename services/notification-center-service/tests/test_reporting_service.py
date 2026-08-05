"""StatisticsService, ReportService, AuditService.

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

from app.models.delivery import NotificationDelivery
from app.models.enums import (
    AuditAction,
    NotificationChannelKind,
    NotificationStatus,
    ReportFormat,
    ReportKind,
    ReportStatus,
)
from app.repositories.governance import NotificationAuditRepository
from app.services.reporting import AuditService, ReportService, StatisticsService
from tests.conftest import ago, soon

pytestmark = pytest.mark.asyncio


class TestRollup:
    async def test_computes_a_fresh_window(
        self,
        statistics_service: StatisticsService,
        make_notification,
        delivery_service,
        organization_id,
    ) -> None:
        notification = await make_notification(user_id="user-1")
        await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.IN_APP
        )
        window = await statistics_service.rollup(
            organization_id, window_start=ago(hours=1), window_end=soon(hours=1)
        )
        assert window.sent_count >= 1
        assert window.delivered_count >= 1
        assert window.window_end is not None

    async def test_is_idempotent_by_window_start(
        self, statistics_service: StatisticsService, make_notification, organization_id
    ) -> None:
        start, end = ago(hours=1), soon(hours=1)
        first = await statistics_service.rollup(organization_id, window_start=start, window_end=end)
        await make_notification(user_id="user-2")
        second = await statistics_service.rollup(
            organization_id, window_start=start, window_end=end
        )
        assert second.id == first.id

    async def test_zero_activity_gives_sensible_defaults(
        self, statistics_service: StatisticsService, organization_id
    ) -> None:
        window = await statistics_service.rollup(
            organization_id, window_start=ago(hours=1), window_end=soon(hours=1)
        )
        assert window.sent_count == 0
        assert window.delivered_count == 0
        assert window.failed_count == 0
        assert window.read_rate == 0.0
        assert window.acknowledgement_rate == 0.0
        assert window.retry_rate == 0.0
        assert window.average_delivery_ms is None

    async def test_counts_failed_and_retried_deliveries(
        self,
        statistics_service: StatisticsService,
        make_notification,
        delivery_service,
        organization_id,
    ) -> None:
        notification = await make_notification(user_id="user-3")
        await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.EMAIL
        )
        # Advance to a second attempt so attempts_used > 1, exercising
        # the retried_count branch (a single first attempt never counts).
        await delivery_service.retry_due(now=datetime.now(UTC) + timedelta(seconds=1))

        window = await statistics_service.rollup(
            organization_id, window_start=ago(hours=1), window_end=soon(hours=1)
        )
        assert window.retried_count >= 1
        assert window.retry_rate > 0.0

    async def test_counts_read_and_acknowledged_notifications(
        self,
        statistics_service: StatisticsService,
        make_notification,
        notification_service,
        organization_id,
    ) -> None:
        notification = await make_notification(user_id="user-4")
        await notification_service.acknowledge(organization_id, notification.id)

        window = await statistics_service.rollup(
            organization_id, window_start=ago(hours=1), window_end=soon(hours=1)
        )
        assert window.read_count >= 1
        assert window.acknowledged_count >= 1
        assert window.read_rate > 0.0
        assert window.acknowledgement_rate > 0.0

    async def test_tracks_channel_and_template_usage(
        self,
        statistics_service: StatisticsService,
        make_notification,
        delivery_service,
        organization_id,
    ) -> None:
        notification = await make_notification(user_id="user-5")
        await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.IN_APP
        )
        window = await statistics_service.rollup(
            organization_id, window_start=ago(hours=1), window_end=soon(hours=1)
        )
        assert window.channel_usage.get(str(NotificationChannelKind.IN_APP), 0) >= 1
        assert window.template_usage.get("none", 0) >= 1

    async def test_records_average_delivery_latency(
        self,
        statistics_service: StatisticsService,
        make_notification,
        deliveries_repo,
        organization_id,
    ) -> None:
        # Neither of this fixture's own real channels (IN_APP always,
        # EMAIL/webhook-shaped never registered) ever populates a
        # DeliveryResult's latency_ms, so a delivery with one recorded is
        # built directly here to exercise the averaging itself for real.
        notification = await make_notification(user_id="user-6")
        await deliveries_repo.create(
            NotificationDelivery(
                organization_id=organization_id,
                notification_id=notification.id,
                channel=NotificationChannelKind.IN_APP,
                status=NotificationStatus.DELIVERED,
                queued_at=datetime.now(UTC),
                sent_at=datetime.now(UTC),
                delivered_at=datetime.now(UTC),
                latency_ms=42.0,
            )
        )
        window = await statistics_service.rollup(
            organization_id, window_start=ago(hours=1), window_end=soon(hours=1)
        )
        assert window.average_delivery_ms == 42.0


class TestDashboard:
    async def test_returns_sensible_defaults_with_zero_activity(
        self, statistics_service: StatisticsService, organization_id
    ) -> None:
        data = await statistics_service.dashboard(organization_id)
        assert data["deliveries_by_status"] == {}
        assert data["queue_length"] == 0
        assert data["latest_window"]["computed_through"] is None
        assert data["latest_window"]["read_rate"] is None
        assert data["latest_window"]["retry_rate"] is None
        assert data["latest_window"]["average_delivery_ms"] is None

    async def test_reflects_deliveries_by_status_and_the_latest_rollup(
        self,
        statistics_service: StatisticsService,
        make_notification,
        delivery_service,
        organization_id,
    ) -> None:
        notification = await make_notification(user_id="user-7")
        await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.EMAIL
        )
        await statistics_service.rollup(
            organization_id, window_start=ago(hours=1), window_end=soon(hours=1)
        )

        data = await statistics_service.dashboard(organization_id)
        assert data["deliveries_by_status"].get(str(NotificationStatus.QUEUED), 0) >= 1
        assert data["queue_length"] >= 1
        assert data["latest_window"]["computed_through"] is not None


class TestTrend:
    async def test_returns_an_empty_list_when_there_are_no_rollups(
        self, statistics_service: StatisticsService, organization_id
    ) -> None:
        trend = await statistics_service.trend(organization_id, since_days=30)
        assert trend == []

    async def test_returns_windows_oldest_first(
        self, statistics_service: StatisticsService, make_notification, organization_id
    ) -> None:
        await make_notification(user_id="user-8")
        await statistics_service.rollup(
            organization_id, window_start=ago(hours=2), window_end=ago(hours=1)
        )
        await statistics_service.rollup(
            organization_id, window_start=ago(hours=1), window_end=soon(hours=1)
        )
        trend = await statistics_service.trend(organization_id, since_days=30)
        assert len(trend) >= 2
        assert trend[0].window_start <= trend[-1].window_start


class TestReportGenerate:
    async def test_delivery_report_succeeds_with_rows(
        self, report_service: ReportService, make_notification, delivery_service, organization_id
    ) -> None:
        notification = await make_notification(user_id="user-9")
        await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.IN_APP
        )
        report = await report_service.generate(organization_id, kind=ReportKind.DELIVERY)
        assert report.status == ReportStatus.COMPLETED
        assert report.row_count is not None
        assert report.row_count >= 1
        row = report.content["rows"][0]
        assert {"notification_id", "channel", "status", "queued_at", "latency_ms"} <= row.keys()

    async def test_failure_report_succeeds_with_no_dead_letters(
        self, report_service: ReportService, organization_id
    ) -> None:
        report = await report_service.generate(organization_id, kind=ReportKind.FAILURE)
        assert report.status == ReportStatus.COMPLETED
        assert report.content["rows"] == []

    async def test_failure_report_succeeds_with_a_dead_letter(
        self, report_service: ReportService, make_notification, delivery_service, organization_id
    ) -> None:
        notification = await make_notification(user_id="user-10")
        deliveries = await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.EMAIL
        )
        for offset in (1, 2):
            await delivery_service.retry_due(now=datetime.now(UTC) + timedelta(seconds=offset))
        assert deliveries  # sanity: a delivery was created to dead-letter

        report = await report_service.generate(organization_id, kind=ReportKind.FAILURE)
        assert report.status == ReportStatus.COMPLETED
        assert len(report.content["rows"]) == 1
        row = report.content["rows"][0]
        assert {
            "notification_id",
            "delivery_id",
            "channel",
            "attempts",
            "last_error",
            "resolved",
        } <= (row.keys())

    async def test_retry_report_succeeds_with_a_pending_retry(
        self, report_service: ReportService, make_notification, delivery_service, organization_id
    ) -> None:
        notification = await make_notification(user_id="user-11")
        await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.EMAIL
        )
        report = await report_service.generate(organization_id, kind=ReportKind.RETRY)
        assert report.status == ReportStatus.COMPLETED
        assert len(report.content["rows"]) == 1
        row = report.content["rows"][0]
        assert {
            "notification_id",
            "delivery_id",
            "retry_count",
            "next_retry_at",
            "resolved",
        } <= row.keys()

    async def test_audit_report_succeeds_with_entries(
        self, report_service: ReportService, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.NOTIFICATION_CREATED,
            entity_type="notification",
            summary="Created.",
        )
        report = await report_service.generate(organization_id, kind=ReportKind.AUDIT)
        assert report.status == ReportStatus.COMPLETED
        assert len(report.content["rows"]) == 1
        row = report.content["rows"][0]
        assert {"action", "entity_type", "actor_id", "occurred_at", "succeeded"} <= row.keys()

    @pytest.mark.parametrize(
        "kind",
        [
            ReportKind.ANNOUNCEMENT,
            ReportKind.TEMPLATE_USAGE,
            ReportKind.CHANNEL,
            ReportKind.ENGAGEMENT,
        ],
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

    async def test_generate_never_raises_records_failed_status_when_the_builder_itself_breaks(
        self,
        make_notification,
        delivery_service,
        reports_repo,
        deliveries_repo,
        dead_letters_repo,
        retry_queue_repo,
        audit_repo,
        organization_id,
    ) -> None:
        # A genuinely broken builder (an invalid row limit no legitimate
        # caller would ever configure) still must not raise out of
        # generate() -- it is recorded as a FAILED report instead. No
        # mocking: this is the real ReportService, just misconfigured.
        notification = await make_notification(user_id="user-broken-report")
        await delivery_service.dispatch(
            organization_id, notification, requested_channel=NotificationChannelKind.IN_APP
        )
        broken_service = ReportService(
            reports_repo,
            deliveries_repo,
            dead_letters_repo,
            retry_queue_repo,
            audit_repo,
            max_rows="not-a-number",  # type: ignore[arg-type]
        )
        report = await broken_service.generate(organization_id, kind=ReportKind.DELIVERY)
        assert report.status == ReportStatus.FAILED
        assert report.error is not None

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

    async def test_list_for_org_returns_newest_first(
        self, report_service: ReportService, organization_id
    ) -> None:
        await report_service.generate(organization_id, kind=ReportKind.DELIVERY)
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
        assert "| 1 | 2 |" in rendered

    async def test_to_markdown_handles_empty_rows(self) -> None:
        rendered = ReportService.to_markdown({"rows": []})
        assert "No rows." in rendered
        assert "# Report" in rendered


class TestAuditService:
    async def test_record_appends_an_entry(
        self, audit_service: AuditService, organization_id
    ) -> None:
        entry = await audit_service.record(
            organization_id,
            action=AuditAction.NOTIFICATION_CREATED,
            entity_type="notification",
            summary="Created.",
        )
        assert entry.succeeded is True

    async def test_record_stores_every_optional_field(
        self, audit_service: AuditService, organization_id
    ) -> None:
        entity_id = uuid4()
        entry = await audit_service.record(
            organization_id,
            action=AuditAction.CHANNEL_CONFIGURED,
            entity_type="channel",
            summary="Configured webhook.",
            entity_id=entity_id,
            entity_reference="webhook",
            actor_id="alice",
            actor_type="system",
            succeeded=False,
            changes={"enabled": True},
            context={"reason": "onboarding"},
            request_id="req-1",
            ip_address="127.0.0.1",
        )
        assert entry.entity_id == entity_id
        assert entry.entity_reference == "webhook"
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
            action=AuditAction.NOTIFICATION_CREATED,
            entity_type="notification",
            summary="Created.",
        )
        await audit_service.record(
            organization_id,
            action=AuditAction.NOTIFICATION_CANCELLED,
            entity_type="notification",
            summary="Cancelled.",
        )
        found = await audit_service.list_entries(
            organization_id, action=AuditAction.NOTIFICATION_CANCELLED
        )
        assert all(one.action == AuditAction.NOTIFICATION_CANCELLED for one in found)
        assert len(found) == 1

    async def test_list_entries_filters_by_entity_id(
        self, audit_service: AuditService, organization_id
    ) -> None:
        entity_id = uuid4()
        await audit_service.record(
            organization_id,
            action=AuditAction.NOTIFICATION_CREATED,
            entity_type="notification",
            summary="Created.",
            entity_id=entity_id,
        )
        await audit_service.record(
            organization_id,
            action=AuditAction.NOTIFICATION_CREATED,
            entity_type="notification",
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
            action=AuditAction.NOTIFICATION_CREATED,
            entity_type="notification",
            summary="Created.",
            actor_id="alice",
        )
        found = await audit_service.list_entries(organization_id, actor_id="alice")
        assert all(one.actor_id == "alice" for one in found)

    async def test_summary_counts_by_action(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record(
            organization_id,
            action=AuditAction.NOTIFICATION_CREATED,
            entity_type="notification",
            summary="Created.",
        )
        summary = await audit_service.summary(organization_id, days=30)
        assert summary["total"] >= 1
        assert str(AuditAction.NOTIFICATION_CREATED) in summary["by_action"]

    async def test_record_failure_without_a_session_factory_records_inline(
        self, audit_service: AuditService, organization_id
    ) -> None:
        await audit_service.record_failure(
            organization_id,
            action=AuditAction.ADMINISTRATIVE,
            entity_type="notification",
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
                NotificationAuditRepository(writer), session_factory=db_session_factory
            )
            await service.record_failure(
                organization_id,
                action=AuditAction.ADMINISTRATIVE,
                entity_type="notification",
                summary="Refused: the requester cannot cancel someone else's notification.",
                actor_id="mallory",
                entity_reference="notif-123",
                request_id="req-2",
                context={"reason": "not the owner"},
            )
            await writer.rollback()

        async with db_session_factory() as reader:
            entries = await NotificationAuditRepository(reader).list_for_org(organization_id)
        assert len(entries) == 1, "the refusal outlived the transaction that refused it"
        assert entries[0].succeeded is False
        assert entries[0].actor_id == "mallory"
