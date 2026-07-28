"""Tests for the pure decision engines.

These need no database: every engine here is deliberately
side-effect-free over already-fetched rows, which is exactly what
makes them directly testable at this level.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.enums.severity import Severity

from app.correlation.engine import correlate
from app.deduplication.fingerprint import compute_fingerprint
from app.escalation.engine import due_level, parse_levels
from app.escalation.oncall import resolve_oncall
from app.models.alert_condition import AlertCondition
from app.models.alert_instance import AlertInstance
from app.models.alert_maintenance_window import AlertMaintenanceWindow
from app.models.alert_oncall_schedule import AlertOnCallSchedule
from app.models.alert_route import AlertRoute
from app.models.alert_rule import AlertRule
from app.models.alert_suppression import AlertSuppression
from app.models.enums import (
    AlertRouteChannel,
    AlertRuleType,
    AlertSource,
    AlertStatus,
    BooleanOperator,
    MaintenanceWindowScope,
    MaintenanceWindowType,
    OnCallRotationType,
    RouteTargetType,
    SuppressionType,
)
from app.routing.engine import route_matches, select_routes
from app.rules.evaluator import evaluate_expression, evaluate_rule
from app.suppression.engine import evaluate_suppression
from app.suppression.maintenance import is_window_active

ORG = uuid.uuid4()


class TestFingerprint:
    def test_same_condition_yields_same_fingerprint(self) -> None:
        args = {
            "organization_id": ORG,
            "source": AlertSource.MONITORING,
            "rule_id": None,
            "source_reference": {"target_id": "abc"},
        }
        assert compute_fingerprint(**args) == compute_fingerprint(**args)

    def test_ignores_non_identity_keys(self) -> None:
        """A per-occurrence value must not change identity, or dedup breaks."""
        base = {
            "organization_id": ORG,
            "source": AlertSource.MONITORING,
            "rule_id": None,
        }
        first = compute_fingerprint(**base, source_reference={"target_id": "abc", "value": 1})
        second = compute_fingerprint(**base, source_reference={"target_id": "abc", "value": 999})
        assert first == second

    def test_different_target_yields_different_fingerprint(self) -> None:
        base = {
            "organization_id": ORG,
            "source": AlertSource.MONITORING,
            "rule_id": None,
        }
        first = compute_fingerprint(**base, source_reference={"target_id": "abc"})
        second = compute_fingerprint(**base, source_reference={"target_id": "xyz"})
        assert first != second

    def test_different_organization_yields_different_fingerprint(self) -> None:
        reference = {"target_id": "abc"}
        first = compute_fingerprint(
            organization_id=ORG,
            source=AlertSource.MONITORING,
            rule_id=None,
            source_reference=reference,
        )
        second = compute_fingerprint(
            organization_id=uuid.uuid4(),
            source=AlertSource.MONITORING,
            rule_id=None,
            source_reference=reference,
        )
        assert first != second

    def test_is_stable_across_key_ordering(self) -> None:
        base = {
            "organization_id": ORG,
            "source": AlertSource.MONITORING,
            "rule_id": None,
        }
        first = compute_fingerprint(**base, source_reference={"target_id": "abc", "metric_id": "m"})
        second = compute_fingerprint(
            **base, source_reference={"metric_id": "m", "target_id": "abc"}
        )
        assert first == second


def _rule(operator: BooleanOperator = BooleanOperator.AND) -> AlertRule:
    return AlertRule(
        organization_id=ORG,
        name="r",
        rule_type=AlertRuleType.METRIC_THRESHOLD,
        source=AlertSource.MONITORING,
        boolean_operator=operator,
        severity=Severity.HIGH,
    )


def _condition(expression: str, sequence: int = 0) -> AlertCondition:
    return AlertCondition(
        organization_id=ORG, rule_id=uuid.uuid4(), sequence=sequence, expression=expression
    )


class TestRuleEvaluator:
    def test_and_requires_every_condition(self) -> None:
        rule = _rule(BooleanOperator.AND)
        conditions = [_condition("value > 10"), _condition("value < 100", 1)]
        assert evaluate_rule(rule, conditions, {"value": 50}) is True
        assert evaluate_rule(rule, conditions, {"value": 500}) is False

    def test_or_requires_only_one(self) -> None:
        rule = _rule(BooleanOperator.OR)
        conditions = [_condition("value > 100"), _condition("value < 5", 1)]
        assert evaluate_rule(rule, conditions, {"value": 1}) is True
        assert evaluate_rule(rule, conditions, {"value": 50}) is False

    def test_rule_with_no_conditions_never_fires(self) -> None:
        """An unconfigured rule must not raise a confident false alert."""
        assert evaluate_rule(_rule(), [], {"value": 1}) is False

    def test_malformed_expression_does_not_fire(self) -> None:
        assert evaluate_expression("value >", {"value": 1}) is False

    def test_missing_variable_does_not_fire(self) -> None:
        assert evaluate_expression("absent > 1", {}) is False


def _window(
    *,
    window_type: MaintenanceWindowType,
    starts_at: datetime,
    ends_at: datetime,
    recurrence_rule: str | None = None,
    enabled: bool = True,
) -> AlertMaintenanceWindow:
    return AlertMaintenanceWindow(
        organization_id=ORG,
        name="w",
        window_type=window_type,
        scope=MaintenanceWindowScope.ORGANIZATION,
        recurrence_rule=recurrence_rule,
        starts_at=starts_at,
        ends_at=ends_at,
        enabled=enabled,
    )


class TestMaintenanceWindow:
    def test_scheduled_window_active_inside_interval(self) -> None:
        now = datetime.now(UTC)
        window = _window(
            window_type=MaintenanceWindowType.SCHEDULED,
            starts_at=now - timedelta(minutes=5),
            ends_at=now + timedelta(minutes=5),
        )
        assert is_window_active(window, now) is True

    def test_scheduled_window_inactive_after_interval(self) -> None:
        now = datetime.now(UTC)
        window = _window(
            window_type=MaintenanceWindowType.SCHEDULED,
            starts_at=now - timedelta(hours=2),
            ends_at=now - timedelta(hours=1),
        )
        assert is_window_active(window, now) is False

    def test_disabled_window_never_active(self) -> None:
        now = datetime.now(UTC)
        window = _window(
            window_type=MaintenanceWindowType.SCHEDULED,
            starts_at=now - timedelta(minutes=5),
            ends_at=now + timedelta(minutes=5),
            enabled=False,
        )
        assert is_window_active(window, now) is False

    def test_daily_recurrence_active_in_later_occurrence(self) -> None:
        start = datetime(2026, 1, 1, 2, 0, tzinfo=UTC)
        window = _window(
            window_type=MaintenanceWindowType.RECURRING,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            recurrence_rule="FREQ=DAILY",
        )
        # 10 days later, 30 minutes into that day's own occurrence.
        assert is_window_active(window, start + timedelta(days=10, minutes=30)) is True
        # Same day, outside the one-hour occurrence.
        assert is_window_active(window, start + timedelta(days=10, hours=5)) is False

    def test_interval_recurrence_skips_off_periods(self) -> None:
        start = datetime(2026, 1, 1, 2, 0, tzinfo=UTC)
        window = _window(
            window_type=MaintenanceWindowType.RECURRING,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            recurrence_rule="FREQ=DAILY;INTERVAL=2",
        )
        assert is_window_active(window, start + timedelta(days=2, minutes=10)) is True
        assert is_window_active(window, start + timedelta(days=1, minutes=10)) is False

    def test_unparseable_recurrence_falls_back_to_stored_interval(self) -> None:
        """Fail safe: never suppress forever on a rule we cannot read."""
        start = datetime(2026, 1, 1, 2, 0, tzinfo=UTC)
        window = _window(
            window_type=MaintenanceWindowType.RECURRING,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            recurrence_rule="FREQ=FORTNIGHTLY",
        )
        assert is_window_active(window, start + timedelta(minutes=30)) is True
        assert is_window_active(window, start + timedelta(days=10)) is False

    def test_zero_length_recurring_window_never_active(self) -> None:
        start = datetime(2026, 1, 1, 2, 0, tzinfo=UTC)
        window = _window(
            window_type=MaintenanceWindowType.RECURRING,
            starts_at=start,
            ends_at=start,
            recurrence_rule="FREQ=DAILY",
        )
        assert is_window_active(window, start) is False


class TestSuppressionEngine:
    def test_no_rules_means_not_suppressed(self) -> None:
        decision = evaluate_suppression(
            source_reference={"target_id": "abc"},
            suppressions=[],
            maintenance_windows=[],
            moment=datetime.now(UTC),
        )
        assert decision.suppressed is False

    def test_maintenance_window_wins_over_suppression_rule(self) -> None:
        now = datetime.now(UTC)
        window = _window(
            window_type=MaintenanceWindowType.SCHEDULED,
            starts_at=now - timedelta(minutes=1),
            ends_at=now + timedelta(minutes=1),
        )
        suppression = AlertSuppression(
            organization_id=ORG,
            suppression_type=SuppressionType.MANUAL,
            starts_at=now - timedelta(minutes=1),
        )
        decision = evaluate_suppression(
            source_reference={"target_id": "abc"},
            suppressions=[suppression],
            maintenance_windows=[window],
            moment=now,
        )
        assert decision.suppression_type is SuppressionType.MAINTENANCE_WINDOW

    def test_scoped_suppression_only_matches_its_own_target(self) -> None:
        now = datetime.now(UTC)
        suppression = AlertSuppression(
            organization_id=ORG,
            suppression_type=SuppressionType.MANUAL,
            scope_reference="abc",
            starts_at=now - timedelta(minutes=1),
        )
        matched = evaluate_suppression(
            source_reference={"target_id": "abc"},
            suppressions=[suppression],
            maintenance_windows=[],
            moment=now,
        )
        unmatched = evaluate_suppression(
            source_reference={"target_id": "other"},
            suppressions=[suppression],
            maintenance_windows=[],
            moment=now,
        )
        assert matched.suppressed is True
        assert unmatched.suppressed is False

    def test_unscoped_suppression_is_organization_wide(self) -> None:
        now = datetime.now(UTC)
        suppression = AlertSuppression(
            organization_id=ORG,
            suppression_type=SuppressionType.RULE_BASED,
            starts_at=now - timedelta(minutes=1),
        )
        decision = evaluate_suppression(
            source_reference={"anything": "at-all"},
            suppressions=[suppression],
            maintenance_windows=[],
            moment=now,
        )
        assert decision.suppressed is True


def _alert(
    *, severity: Severity, triggered_at: datetime, reference: dict[str, str] | None = None
) -> AlertInstance:
    alert = AlertInstance(
        organization_id=ORG,
        source=AlertSource.MONITORING,
        severity=severity,
        status=AlertStatus.OPEN,
        title="t",
        message="m",
        fingerprint=uuid.uuid4().hex,
        source_reference=reference or {},
        triggered_at=triggered_at,
    )
    alert.id = uuid.uuid4()
    return alert


class TestCorrelationEngine:
    def test_shared_reference_beats_time_only_match(self) -> None:
        now = datetime.now(UTC)
        subject = _alert(severity=Severity.HIGH, triggered_at=now, reference={"target_id": "db-1"})
        time_only = _alert(severity=Severity.CRITICAL, triggered_at=now - timedelta(seconds=30))
        shared = _alert(
            severity=Severity.LOW,
            triggered_at=now - timedelta(seconds=60),
            reference={"target_id": "db-1"},
        )
        decision = correlate(subject, [time_only, shared], window=timedelta(minutes=5))
        assert decision is not None
        assert decision.parent.id == shared.id

    def test_most_severe_wins_among_equal_matches(self) -> None:
        now = datetime.now(UTC)
        subject = _alert(severity=Severity.HIGH, triggered_at=now)
        low = _alert(severity=Severity.LOW, triggered_at=now - timedelta(seconds=10))
        critical = _alert(severity=Severity.CRITICAL, triggered_at=now - timedelta(seconds=20))
        decision = correlate(subject, [low, critical], window=timedelta(minutes=5))
        assert decision is not None
        assert decision.parent.id == critical.id

    def test_never_correlates_to_itself(self) -> None:
        now = datetime.now(UTC)
        subject = _alert(severity=Severity.HIGH, triggered_at=now)
        assert correlate(subject, [subject], window=timedelta(minutes=5)) is None

    def test_ignores_alerts_outside_the_window(self) -> None:
        now = datetime.now(UTC)
        subject = _alert(severity=Severity.HIGH, triggered_at=now)
        old = _alert(severity=Severity.CRITICAL, triggered_at=now - timedelta(hours=2))
        assert correlate(subject, [old], window=timedelta(minutes=5)) is None

    def test_ignores_alerts_triggered_after_the_subject(self) -> None:
        """A later alert cannot be an earlier one's own root cause."""
        now = datetime.now(UTC)
        subject = _alert(severity=Severity.HIGH, triggered_at=now)
        later = _alert(severity=Severity.CRITICAL, triggered_at=now + timedelta(seconds=30))
        assert correlate(subject, [later], window=timedelta(minutes=5)) is None


def _route(*, severity_filter: Severity | None = None, enabled: bool = True) -> AlertRoute:
    return AlertRoute(
        organization_id=ORG,
        name="r",
        channel=AlertRouteChannel.EMAIL,
        target_type=RouteTargetType.USER,
        target_reference=str(uuid.uuid4()),
        severity_filter=severity_filter,
        enabled=enabled,
    )


class TestRoutingEngine:
    def test_unfiltered_route_matches_every_severity(self) -> None:
        route = _route()
        assert route_matches(route, Severity.INFO) is True
        assert route_matches(route, Severity.CRITICAL) is True

    def test_filtered_route_also_matches_more_severe(self) -> None:
        """A HIGH-filtered route must never let a CRITICAL slip past."""
        route = _route(severity_filter=Severity.HIGH)
        assert route_matches(route, Severity.CRITICAL) is True
        assert route_matches(route, Severity.HIGH) is True
        assert route_matches(route, Severity.MEDIUM) is False

    def test_disabled_route_never_matches(self) -> None:
        assert route_matches(_route(enabled=False), Severity.CRITICAL) is False

    def test_select_routes_filters_the_collection(self) -> None:
        routes = [
            _route(severity_filter=Severity.CRITICAL),
            _route(severity_filter=Severity.LOW),
            _route(enabled=False),
        ]
        assert len(select_routes(routes, Severity.HIGH)) == 1


class TestEscalationEngine:
    def test_cumulative_delays_accumulate_down_the_chain(self) -> None:
        levels = parse_levels(
            [
                {"target_type": "user", "target_reference": "a", "delay_seconds": 300},
                {"target_type": "manager", "target_reference": "b", "delay_seconds": 600},
            ]
        )
        assert [level.cumulative_delay_seconds for level in levels] == [300.0, 900.0]

    def test_malformed_levels_are_skipped_not_fatal(self) -> None:
        levels = parse_levels(
            [
                {"target_type": "user", "target_reference": "a", "delay_seconds": 60},
                {"target_type": "not-a-type", "target_reference": "b", "delay_seconds": 60},
                {"target_type": "user", "delay_seconds": 60},
                {"target_type": "user", "target_reference": "c", "delay_seconds": -1},
                {"target_type": "user", "target_reference": "d", "delay_seconds": "abc"},
            ]
        )
        assert [level.target_reference for level in levels] == ["a"]

    def test_due_level_returns_furthest_reached(self) -> None:
        levels = parse_levels(
            [
                {"target_type": "user", "target_reference": "a", "delay_seconds": 60},
                {"target_type": "user", "target_reference": "b", "delay_seconds": 60},
                {"target_type": "user", "target_reference": "c", "delay_seconds": 60},
            ]
        )
        level = due_level(levels, 130)
        assert level is not None
        assert level.target_reference == "b"

    def test_no_level_due_before_first_delay(self) -> None:
        levels = parse_levels(
            [{"target_type": "user", "target_reference": "a", "delay_seconds": 300}]
        )
        assert due_level(levels, 10) is None

    def test_empty_chain_has_no_due_level(self) -> None:
        assert due_level([], 10_000) is None


def _schedule(
    *,
    participants: list[str],
    created_at: datetime,
    rotation_type: OnCallRotationType = OnCallRotationType.WEEKLY,
    overrides: list[dict[str, str]] | None = None,
    holidays: list[str] | None = None,
    enabled: bool = True,
) -> AlertOnCallSchedule:
    schedule = AlertOnCallSchedule(
        organization_id=ORG,
        name="s",
        rotation_type=rotation_type,
        timezone="UTC",
        participants=participants,
        overrides=overrides or [],
        holiday_calendar=holidays or [],
        enabled=enabled,
    )
    schedule.created_at = created_at
    return schedule


class TestOnCallResolution:
    def test_rotation_advances_by_period(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        schedule = _schedule(participants=["u1", "u2"], created_at=start)
        assert resolve_oncall(schedule, start + timedelta(days=1)) == "u1"
        assert resolve_oncall(schedule, start + timedelta(weeks=1)) == "u2"
        assert resolve_oncall(schedule, start + timedelta(weeks=2)) == "u1"

    def test_override_beats_computed_rotation(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        moment = start + timedelta(days=1)
        schedule = _schedule(
            participants=["u1", "u2"],
            created_at=start,
            overrides=[
                {
                    "user_id": "cover",
                    "starts_at": (moment - timedelta(hours=1)).isoformat(),
                    "ends_at": (moment + timedelta(hours=1)).isoformat(),
                }
            ],
        )
        assert resolve_oncall(schedule, moment) == "cover"

    def test_holiday_means_nobody_is_on_call(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        moment = start + timedelta(days=1)
        schedule = _schedule(
            participants=["u1"], created_at=start, holidays=[moment.date().isoformat()]
        )
        assert resolve_oncall(schedule, moment) is None

    def test_disabled_or_empty_schedule_returns_none(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        assert (
            resolve_oncall(_schedule(participants=["u"], created_at=start, enabled=False), start)
            is None
        )
        assert resolve_oncall(_schedule(participants=[], created_at=start), start) is None

    def test_malformed_override_is_ignored(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        schedule = _schedule(
            participants=["u1"],
            created_at=start,
            overrides=[
                {"user_id": "x", "starts_at": "not-a-date", "ends_at": "also-not"},
                {"starts_at": start.isoformat(), "ends_at": start.isoformat()},
            ],
        )
        assert resolve_oncall(schedule, start + timedelta(days=1)) == "u1"

    def test_moment_before_creation_uses_first_participant(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        schedule = _schedule(participants=["u1", "u2"], created_at=start)
        assert resolve_oncall(schedule, start - timedelta(days=1)) == "u1"

    @pytest.mark.parametrize(
        "rotation",
        [
            OnCallRotationType.DAILY,
            OnCallRotationType.WEEKLY,
            OnCallRotationType.BIWEEKLY,
            OnCallRotationType.CUSTOM,
        ],
    )
    def test_every_rotation_type_resolves(self, rotation: OnCallRotationType) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        schedule = _schedule(participants=["u1", "u2"], created_at=start, rotation_type=rotation)
        assert resolve_oncall(schedule, start + timedelta(hours=1)) == "u1"
