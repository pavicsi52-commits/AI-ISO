"""Tests for the supporting services: rules, suppression, maintenance
windows, on-call, routes, escalation policies, acknowledgements,
audit, correlation, deduplication, statistics, reports, and dispatch.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.enums.severity import Severity
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError
from shared_core.notifications.factory import create_notification_framework
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    AlertReportType,
    AlertRouteChannel,
    AlertRuleType,
    AlertSource,
    AlertStatus,
    AuditOutcome,
    BooleanOperator,
    CorrelationType,
    EscalationTargetType,
    MaintenanceWindowScope,
    MaintenanceWindowType,
    NotificationDeliveryStatus,
    OnCallRotationType,
    RouteTargetType,
    SuppressionType,
)
from app.notifications.alert_notifications import AlertNotificationService
from app.repositories.alert_acknowledgement import AlertAcknowledgementRepository
from app.repositories.alert_audit import AlertAuditEntryRepository
from app.repositories.alert_condition import AlertConditionRepository
from app.repositories.alert_correlation import AlertCorrelationRepository
from app.repositories.alert_escalation import AlertEscalationPolicyRepository
from app.repositories.alert_history import AlertHistoryRepository
from app.repositories.alert_instance import AlertInstanceRepository
from app.repositories.alert_maintenance_window import AlertMaintenanceWindowRepository
from app.repositories.alert_notification import AlertNotificationRepository
from app.repositories.alert_oncall_schedule import AlertOnCallScheduleRepository
from app.repositories.alert_report import AlertReportRepository
from app.repositories.alert_route import AlertRouteRepository
from app.repositories.alert_rule import AlertRuleRepository
from app.repositories.alert_statistics import AlertStatisticsRepository
from app.repositories.alert_suppression import AlertSuppressionRepository
from app.schemas.escalation import EscalationLevelRequest
from app.schemas.rule import AlertConditionCreateRequest
from app.services.acknowledgement import AlertAcknowledgementService
from app.services.alert import AlertService
from app.services.audit import AlertAuditService
from app.services.correlation import AlertCorrelationService
from app.services.dispatch import AlertDispatchService
from app.services.escalation import AlertEscalationPolicyService
from app.services.maintenance_window import AlertMaintenanceWindowService
from app.services.oncall import AlertOnCallScheduleService
from app.services.report import AlertReportService
from app.services.route import AlertRouteService
from app.services.rule import AlertRuleService
from app.services.statistics import AlertStatisticsService
from app.services.suppression import AlertSuppressionService
from tests.conftest import (
    make_alert,
    make_escalation_policy,
    make_maintenance_window,
    make_oncall_schedule,
    make_route,
    make_suppression,
)


async def _noop_publish(_event: object) -> None:
    return None


class TestRuleService:
    async def test_create_persists_rule_and_conditions(self, db_session: AsyncSession) -> None:
        service = AlertRuleService(
            AlertRuleRepository(db_session), AlertConditionRepository(db_session)
        )
        org = uuid.uuid4()
        rule, conditions = await service.create(
            organization_id=org,
            project_id=None,
            name="cpu",
            description=None,
            rule_type=AlertRuleType.METRIC_THRESHOLD,
            source=AlertSource.MONITORING,
            boolean_operator=BooleanOperator.AND,
            severity=Severity.HIGH,
            window_seconds=None,
            tags={},
            enabled=True,
            conditions=[
                AlertConditionCreateRequest(sequence=0, expression="value > 90"),
                AlertConditionCreateRequest(sequence=1, expression="value < 100"),
            ],
        )
        assert len(conditions) == 2
        assert [c.sequence for c in await service.list_conditions(rule.id)] == [0, 1]

    async def test_list_enabled_for_source_filters(self, db_session: AsyncSession) -> None:
        service = AlertRuleService(
            AlertRuleRepository(db_session), AlertConditionRepository(db_session)
        )
        org = uuid.uuid4()
        common = {
            "organization_id": org,
            "project_id": None,
            "description": None,
            "rule_type": AlertRuleType.METRIC_THRESHOLD,
            "boolean_operator": BooleanOperator.AND,
            "severity": Severity.HIGH,
            "window_seconds": None,
            "tags": {},
            "conditions": [],
        }
        await service.create(name="a", source=AlertSource.MONITORING, enabled=True, **common)
        await service.create(name="b", source=AlertSource.MONITORING, enabled=False, **common)
        await service.create(name="c", source=AlertSource.VALIDATION, enabled=True, **common)

        matching = await service.list_enabled_for_source(org, AlertSource.MONITORING)
        assert [rule.name for rule in matching] == ["a"]


class TestMaintenanceWindowService:
    async def test_list_active_evaluates_recurrence(self, db_session: AsyncSession) -> None:
        service = AlertMaintenanceWindowService(AlertMaintenanceWindowRepository(db_session))
        org = uuid.uuid4()
        now = datetime.now(UTC)
        await make_maintenance_window(
            db_session,
            organization_id=org,
            starts_at=now - timedelta(minutes=1),
            ends_at=now + timedelta(minutes=1),
        )
        await make_maintenance_window(
            db_session,
            organization_id=org,
            starts_at=now - timedelta(days=3),
            ends_at=now - timedelta(days=2),
        )
        assert len(await service.list_for_org(org)) == 2
        assert len(await service.list_active(org)) == 1

    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        service = AlertMaintenanceWindowService(AlertMaintenanceWindowRepository(db_session))
        now = datetime.now(UTC)
        window = await service.create(
            organization_id=uuid.uuid4(),
            project_id=None,
            name="patching",
            window_type=MaintenanceWindowType.SCHEDULED,
            scope=MaintenanceWindowScope.ORGANIZATION,
            scope_reference=None,
            recurrence_rule=None,
            starts_at=now,
            ends_at=now + timedelta(hours=1),
            enabled=True,
        )
        assert (await service.get_by_id(window.id)).name == "patching"


class TestOnCallService:
    async def test_current_oncall_resolves_participant(self, db_session: AsyncSession) -> None:
        service = AlertOnCallScheduleService(AlertOnCallScheduleRepository(db_session))
        schedule = await make_oncall_schedule(db_session, participants=["u1", "u2"])
        assert await service.current_oncall(schedule.id) == "u1"

    async def test_create_and_list(self, db_session: AsyncSession) -> None:
        service = AlertOnCallScheduleService(AlertOnCallScheduleRepository(db_session))
        org = uuid.uuid4()
        await service.create(
            organization_id=org,
            project_id=None,
            name="primary",
            rotation_type=OnCallRotationType.DAILY,
            timezone="UTC",
            participants=["u1"],
            overrides=[],
            holiday_calendar=[],
            enabled=True,
        )
        assert len(await service.list_for_org(org)) == 1

    async def test_unknown_schedule_raises(self, db_session: AsyncSession) -> None:
        service = AlertOnCallScheduleService(AlertOnCallScheduleRepository(db_session))
        with pytest.raises(NotFoundError):
            await service.current_oncall(uuid.uuid4())


class TestRouteService:
    async def test_select_for_severity_applies_filter(self, db_session: AsyncSession) -> None:
        service = AlertRouteService(AlertRouteRepository(db_session))
        org = uuid.uuid4()
        await make_route(db_session, organization_id=org, severity_filter=Severity.CRITICAL)
        await make_route(db_session, organization_id=org, severity_filter=None)
        await make_route(db_session, organization_id=org, enabled=False)

        assert len(await service.select_for_severity(org, Severity.LOW)) == 1
        assert len(await service.select_for_severity(org, Severity.CRITICAL)) == 2

    async def test_create_persists(self, db_session: AsyncSession) -> None:
        service = AlertRouteService(AlertRouteRepository(db_session))
        org = uuid.uuid4()
        await service.create(
            organization_id=org,
            project_id=None,
            name="oncall-email",
            channel=AlertRouteChannel.EMAIL,
            target_type=RouteTargetType.USER,
            target_reference="user@example.internal",
            configuration={},
            severity_filter=None,
            enabled=True,
        )
        assert len(await service.list_for_org(org)) == 1


class TestEscalationPolicyService:
    async def test_create_stores_ordered_levels(self, db_session: AsyncSession) -> None:
        service = AlertEscalationPolicyService(AlertEscalationPolicyRepository(db_session))
        policy = await service.create(
            organization_id=uuid.uuid4(),
            project_id=None,
            name="standard",
            levels=[
                EscalationLevelRequest(
                    target_type=EscalationTargetType.USER,
                    target_reference="u1",
                    delay_seconds=300,
                ),
                EscalationLevelRequest(
                    target_type=EscalationTargetType.MANAGER,
                    target_reference="m1",
                    delay_seconds=600,
                ),
            ],
            enabled=True,
        )
        levels = service.levels_for(policy)
        assert [level.cumulative_delay_seconds for level in levels] == [300.0, 900.0]

    async def test_due_level_for_alert_uses_elapsed_time(self, db_session: AsyncSession) -> None:
        service = AlertEscalationPolicyService(AlertEscalationPolicyRepository(db_session))
        policy = await make_escalation_policy(
            db_session,
            levels=[
                {"target_type": "user", "target_reference": "u1", "delay_seconds": 60},
            ],
        )
        alert = await make_alert(db_session, triggered_at=datetime.now(UTC) - timedelta(minutes=5))
        level = service.due_level_for_alert(policy, alert)
        assert level is not None
        assert level.target_reference == "u1"

    async def test_list_enabled_excludes_disabled(self, db_session: AsyncSession) -> None:
        service = AlertEscalationPolicyService(AlertEscalationPolicyRepository(db_session))
        org = uuid.uuid4()
        await make_escalation_policy(db_session, organization_id=org, enabled=True)
        await make_escalation_policy(db_session, organization_id=org, enabled=False)
        assert len(await service.list_for_org(org)) == 2
        assert len(await service.list_enabled_for_org(org)) == 1

    async def test_list_all_enabled_is_cross_tenant(self, db_session: AsyncSession) -> None:
        repository = AlertEscalationPolicyRepository(db_session)
        await make_escalation_policy(db_session, organization_id=uuid.uuid4(), enabled=True)
        await make_escalation_policy(db_session, organization_id=uuid.uuid4(), enabled=True)
        assert len(await repository.list_all_enabled()) >= 2


class TestSuppressionService:
    async def test_decide_reports_maintenance_window(self, db_session: AsyncSession) -> None:
        service = AlertSuppressionService(
            AlertSuppressionRepository(db_session),
            AlertMaintenanceWindowRepository(db_session),
        )
        org = uuid.uuid4()
        await make_maintenance_window(db_session, organization_id=org)
        decision = await service.decide(org, {"target_id": "x"})
        assert decision.suppressed is True
        assert decision.suppression_type is SuppressionType.MAINTENANCE_WINDOW

    async def test_create_and_list(self, db_session: AsyncSession) -> None:
        service = AlertSuppressionService(
            AlertSuppressionRepository(db_session),
            AlertMaintenanceWindowRepository(db_session),
        )
        org = uuid.uuid4()
        await service.create(
            organization_id=org,
            project_id=None,
            suppression_type=SuppressionType.TEMPORARY,
            scope_reference="db-1",
            reason="deploying",
            starts_at=datetime.now(UTC),
            ends_at=None,
            enabled=True,
        )
        assert len(await service.list_for_org(org)) == 1

    async def test_expired_suppression_is_not_active(self, db_session: AsyncSession) -> None:
        service = AlertSuppressionService(
            AlertSuppressionRepository(db_session),
            AlertMaintenanceWindowRepository(db_session),
        )
        org = uuid.uuid4()
        now = datetime.now(UTC)
        await make_suppression(
            db_session,
            organization_id=org,
            starts_at=now - timedelta(hours=2),
            ends_at=now - timedelta(hours=1),
        )
        assert (await service.decide(org, {"target_id": "x"})).suppressed is False


class TestAcknowledgementAndAuditServices:
    async def test_first_acknowledgement_backs_mtta(self, db_session: AsyncSession) -> None:
        service = AlertAcknowledgementService(AlertAcknowledgementRepository(db_session))
        alert = await make_alert(db_session)
        first = await service.record(
            organization_id=alert.organization_id,
            project_id=None,
            alert_id=alert.id,
            acknowledged_by=uuid.uuid4(),
            comment="first",
        )
        await service.record(
            organization_id=alert.organization_id,
            project_id=None,
            alert_id=alert.id,
            acknowledged_by=uuid.uuid4(),
            comment="second",
        )
        earliest = await service.get_first_for_alert(alert.id)
        assert earliest is not None
        assert earliest.id == first.id

    async def test_no_acknowledgement_returns_none(self, db_session: AsyncSession) -> None:
        service = AlertAcknowledgementService(AlertAcknowledgementRepository(db_session))
        assert await service.get_first_for_alert(uuid.uuid4()) is None

    async def test_audit_records_and_lists(self, db_session: AsyncSession) -> None:
        service = AlertAuditService(AlertAuditEntryRepository(db_session))
        org = uuid.uuid4()
        await service.record(
            organization_id=org,
            actor_id=uuid.uuid4(),
            action="rule.created",
            entity_type="AlertRule",
            entity_id=uuid.uuid4(),
            outcome=AuditOutcome.SUCCESS,
            reason="test",
        )
        assert len(await service.list_for_org(org)) == 1


class TestCorrelationService:
    async def test_correlate_is_idempotent(self, db_session: AsyncSession) -> None:
        service = AlertCorrelationService(
            AlertCorrelationRepository(db_session), AlertInstanceRepository(db_session)
        )
        org = uuid.uuid4()
        now = datetime.now(UTC)
        await make_alert(
            db_session,
            organization_id=org,
            source_reference={"target_id": "db-1"},
            triggered_at=now - timedelta(seconds=30),
        )
        child = await make_alert(
            db_session,
            organization_id=org,
            source_reference={"target_id": "db-1"},
            triggered_at=now,
        )

        first = await service.correlate_alert(child, window_seconds=300)
        second = await service.correlate_alert(child, window_seconds=300)
        assert first is not None
        assert second is not None
        assert first.id == second.id

    async def test_no_candidate_returns_none(self, db_session: AsyncSession) -> None:
        service = AlertCorrelationService(
            AlertCorrelationRepository(db_session), AlertInstanceRepository(db_session)
        )
        alert = await make_alert(db_session)
        assert await service.correlate_alert(alert, window_seconds=300) is None

    async def test_list_parents_and_children(self, db_session: AsyncSession) -> None:
        service = AlertCorrelationService(
            AlertCorrelationRepository(db_session), AlertInstanceRepository(db_session)
        )
        org = uuid.uuid4()
        parent = await make_alert(db_session, organization_id=org)
        child = await make_alert(db_session, organization_id=org)
        await service.record_edge(
            child, parent_alert_id=parent.id, correlation_type=CorrelationType.DEPENDENCY
        )
        assert len(await service.list_children(parent.id)) == 1
        assert len(await service.list_parents(child.id)) == 1


class TestStatisticsService:
    def _service(self, db_session: AsyncSession) -> AlertStatisticsService:
        return AlertStatisticsService(
            AlertStatisticsRepository(db_session),
            AlertInstanceRepository(db_session),
            AlertAcknowledgementRepository(db_session),
            AlertHistoryRepository(db_session),
        )

    async def test_empty_organization_yields_zeroes(self, db_session: AsyncSession) -> None:
        snapshot = await self._service(db_session).get_for_org(uuid.uuid4())
        assert snapshot.total_alerts == 0
        assert snapshot.noise_ratio == 0.0

    async def test_counts_and_ratios(self, db_session: AsyncSession) -> None:
        org = uuid.uuid4()
        await make_alert(db_session, organization_id=org, status=AlertStatus.OPEN)
        await make_alert(db_session, organization_id=org, status=AlertStatus.SUPPRESSED)
        snapshot = await self._service(db_session).recompute(org)
        assert snapshot.total_alerts == 2
        assert snapshot.open_alert_count == 1
        assert snapshot.suppression_rate == pytest.approx(0.5)
        assert snapshot.noise_ratio == pytest.approx(0.5)

    async def test_mttr_measured_only_over_resolved_alerts(self, db_session: AsyncSession) -> None:
        org = uuid.uuid4()
        alerts = AlertService(
            AlertInstanceRepository(db_session), AlertHistoryRepository(db_session)
        )
        resolved = await make_alert(
            db_session,
            organization_id=org,
            status=AlertStatus.OPEN,
            triggered_at=datetime.now(UTC) - timedelta(seconds=120),
        )
        await alerts.transition(resolved.id, AlertStatus.RESOLVED)
        await make_alert(db_session, organization_id=org, status=AlertStatus.OPEN)

        snapshot = await self._service(db_session).recompute(org)
        assert snapshot.mttr_seconds > 0

    async def test_recompute_updates_existing_snapshot(self, db_session: AsyncSession) -> None:
        service = self._service(db_session)
        org = uuid.uuid4()
        first = await service.recompute(org)
        await make_alert(db_session, organization_id=org)
        second = await service.recompute(org)
        assert first.id == second.id
        assert second.total_alerts == 1


class TestReportService:
    def _service(self, db_session: AsyncSession) -> AlertReportService:
        alerts = AlertService(
            AlertInstanceRepository(db_session), AlertHistoryRepository(db_session)
        )
        statistics = AlertStatisticsService(
            AlertStatisticsRepository(db_session),
            AlertInstanceRepository(db_session),
            AlertAcknowledgementRepository(db_session),
            AlertHistoryRepository(db_session),
        )
        return AlertReportService(AlertReportRepository(db_session), alerts, statistics)

    @pytest.mark.parametrize(
        "report_type",
        [
            AlertReportType.EXECUTIVE,
            AlertReportType.OPERATIONAL,
            AlertReportType.SLA,
            AlertReportType.ESCALATION,
            AlertReportType.TREND,
            AlertReportType.NOISE_ANALYSIS,
        ],
    )
    async def test_org_scoped_report_types(
        self, db_session: AsyncSession, report_type: AlertReportType
    ) -> None:
        report = await self._service(db_session).generate(
            uuid.uuid4(),
            report_type=report_type,
            alert_id=None,
            parameters={},
            generated_by=None,
        )
        assert report.result != {}

    async def test_alert_report_requires_alert_id(self, db_session: AsyncSession) -> None:
        with pytest.raises(ValidationError):
            await self._service(db_session).generate(
                uuid.uuid4(),
                report_type=AlertReportType.ALERT,
                alert_id=None,
                parameters={},
                generated_by=None,
            )

    async def test_alert_report_includes_transition_count(self, db_session: AsyncSession) -> None:
        alert = await make_alert(db_session)
        report = await self._service(db_session).generate(
            alert.organization_id,
            report_type=AlertReportType.ALERT,
            alert_id=alert.id,
            parameters={},
            generated_by=None,
        )
        assert "transition_count" in report.result

    async def test_list_filters_by_type(self, db_session: AsyncSession) -> None:
        service = self._service(db_session)
        org = uuid.uuid4()
        await service.generate(
            org,
            report_type=AlertReportType.TREND,
            alert_id=None,
            parameters={},
            generated_by=None,
        )
        assert len(await service.list_for_org(org, report_type=AlertReportType.TREND)) == 1
        assert len(await service.list_for_org(org, report_type=AlertReportType.SLA)) == 0


class TestNotificationAndDispatch:
    def _notifications(self, db_session: AsyncSession) -> AlertNotificationService:
        return AlertNotificationService(
            AlertNotificationRepository(db_session),
            create_notification_framework(),
            publish_event=_noop_publish,
        )

    async def test_unsupported_channel_is_recorded_as_failed(
        self, db_session: AsyncSession
    ) -> None:
        """PagerDuty has no shared_core transport -- surfaced, not faked."""
        alert = await make_alert(db_session)
        route = await make_route(
            db_session,
            organization_id=alert.organization_id,
            channel=AlertRouteChannel.PAGERDUTY,
        )
        record = await self._notifications(db_session).deliver(alert, route)
        assert record.status is NotificationDeliveryStatus.FAILED
        assert record.error_message is not None
        assert "PagerDuty".lower() in record.error_message.lower() or "pagerduty" in str(
            record.error_message
        )

    async def test_delivery_failure_is_recorded_not_raised(self, db_session: AsyncSession) -> None:
        """A NotificationManager with no registered provider fails cleanly."""
        alert = await make_alert(db_session)
        route = await make_route(
            db_session, organization_id=alert.organization_id, channel=AlertRouteChannel.EMAIL
        )
        record = await self._notifications(db_session).deliver(alert, route)
        assert record.status is NotificationDeliveryStatus.FAILED
        assert len(await self._notifications(db_session).list_for_alert(alert.id)) == 1

    def _dispatch(self, db_session: AsyncSession) -> AlertDispatchService:
        return AlertDispatchService(
            AlertService(AlertInstanceRepository(db_session), AlertHistoryRepository(db_session)),
            AlertInstanceRepository(db_session),
            AlertRouteService(AlertRouteRepository(db_session)),
            AlertEscalationPolicyService(AlertEscalationPolicyRepository(db_session)),
            AlertOnCallScheduleService(AlertOnCallScheduleRepository(db_session)),
            self._notifications(db_session),
            publish_event=_noop_publish,
        )

    async def test_dispatch_delivers_to_every_matching_route(
        self, db_session: AsyncSession
    ) -> None:
        org = uuid.uuid4()
        alert = await make_alert(db_session, organization_id=org, severity=Severity.CRITICAL)
        await make_route(db_session, organization_id=org, severity_filter=None)
        await make_route(db_session, organization_id=org, severity_filter=Severity.HIGH)
        assert await self._dispatch(db_session).dispatch_alert(alert) == 2

    async def test_no_policies_means_no_escalations(self, db_session: AsyncSession) -> None:
        org = uuid.uuid4()
        await make_alert(db_session, organization_id=org, status=AlertStatus.OPEN)
        assert await self._dispatch(db_session).advance_escalations(org) == 0

    async def test_due_escalation_moves_alert_to_escalated(self, db_session: AsyncSession) -> None:
        org = uuid.uuid4()
        await make_escalation_policy(
            db_session,
            organization_id=org,
            levels=[{"target_type": "user", "target_reference": "u1", "delay_seconds": 60}],
        )
        alert = await make_alert(
            db_session,
            organization_id=org,
            status=AlertStatus.OPEN,
            triggered_at=datetime.now(UTC) - timedelta(minutes=10),
        )
        advanced = await self._dispatch(db_session).advance_escalations(org)
        assert advanced == 1

        refreshed = await AlertInstanceRepository(db_session).require_by_id(alert.id)
        assert refreshed.status == AlertStatus.ESCALATED

    async def test_acknowledged_alert_does_not_escalate(self, db_session: AsyncSession) -> None:
        """Escalating work already underway would page people needlessly."""
        org = uuid.uuid4()
        await make_escalation_policy(
            db_session,
            organization_id=org,
            levels=[{"target_type": "user", "target_reference": "u1", "delay_seconds": 60}],
        )
        await make_alert(
            db_session,
            organization_id=org,
            status=AlertStatus.ACKNOWLEDGED,
            triggered_at=datetime.now(UTC) - timedelta(minutes=10),
        )
        assert await self._dispatch(db_session).advance_escalations(org) == 0

    async def test_oncall_escalation_resolves_the_schedule(self, db_session: AsyncSession) -> None:
        org = uuid.uuid4()
        schedule = await make_oncall_schedule(db_session, organization_id=org, participants=["u1"])
        await make_escalation_policy(
            db_session,
            organization_id=org,
            levels=[
                {
                    "target_type": "oncall_schedule",
                    "target_reference": str(schedule.id),
                    "delay_seconds": 1,
                }
            ],
        )
        await make_alert(
            db_session,
            organization_id=org,
            status=AlertStatus.OPEN,
            triggered_at=datetime.now(UTC) - timedelta(minutes=10),
        )
        assert await self._dispatch(db_session).advance_escalations(org) == 1

    async def test_workflow_escalation_still_escalates_without_a_caller_token(
        self, db_session: AsyncSession
    ) -> None:
        """The documented gap: recorded and logged, never silently faked."""
        org = uuid.uuid4()
        await make_escalation_policy(
            db_session,
            organization_id=org,
            levels=[
                {
                    "target_type": "workflow",
                    "target_reference": str(uuid.uuid4()),
                    "delay_seconds": 1,
                }
            ],
        )
        await make_alert(
            db_session,
            organization_id=org,
            status=AlertStatus.OPEN,
            triggered_at=datetime.now(UTC) - timedelta(minutes=10),
        )
        assert await self._dispatch(db_session).advance_escalations(org) == 1

    async def test_malformed_oncall_reference_is_handled(self, db_session: AsyncSession) -> None:
        org = uuid.uuid4()
        await make_escalation_policy(
            db_session,
            organization_id=org,
            levels=[
                {
                    "target_type": "oncall_schedule",
                    "target_reference": "not-a-uuid",
                    "delay_seconds": 1,
                }
            ],
        )
        await make_alert(
            db_session,
            organization_id=org,
            status=AlertStatus.OPEN,
            triggered_at=datetime.now(UTC) - timedelta(minutes=10),
        )
        assert await self._dispatch(db_session).advance_escalations(org) == 1


class TestNotificationRetry:
    def _notifications(self, db_session: AsyncSession) -> AlertNotificationService:
        return AlertNotificationService(
            AlertNotificationRepository(db_session),
            create_notification_framework(),
            publish_event=_noop_publish,
        )

    async def test_failed_delivery_is_retried(self, db_session: AsyncSession) -> None:
        service = self._notifications(db_session)
        alert = await make_alert(db_session)
        route = await make_route(
            db_session, organization_id=alert.organization_id, channel=AlertRouteChannel.EMAIL
        )
        await service.deliver(alert, route)

        attempted = await service.retry_failed(alert.organization_id)
        assert attempted == 1

        records = await service.list_for_alert(alert.id)
        assert records[0].retry_count == 1
        # ``==`` not ``is``: a String-backed enum column re-read from the
        # database comes back as a plain ``str``, and ``StrEnum`` compares
        # equal to its own value but is not identical to the member. The
        # same platform gotcha prior AI-IOS services documented.
        assert records[0].status == NotificationDeliveryStatus.RETRYING

    async def test_exhausted_record_is_not_retried_forever(self, db_session: AsyncSession) -> None:
        """An unreachable channel must not become an infinite loop."""
        service = self._notifications(db_session)
        alert = await make_alert(db_session)
        route = await make_route(
            db_session, organization_id=alert.organization_id, channel=AlertRouteChannel.EMAIL
        )
        await service.deliver(alert, route)

        for _ in range(3):
            await service.retry_failed(alert.organization_id, max_attempts=3)
        assert await service.retry_failed(alert.organization_id, max_attempts=3) == 0

    async def test_nothing_to_retry_returns_zero(self, db_session: AsyncSession) -> None:
        service = self._notifications(db_session)
        assert await service.retry_failed(uuid.uuid4()) == 0
