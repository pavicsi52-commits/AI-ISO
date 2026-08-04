"""Pure tests for app/scheduling/engine.py -- no database, no fixtures."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from shared_core.exceptions.validation import ValidationError

from app.models.enums import CalendarRuleKind, ExecutionStatus, JobPriority, ScheduledJobStatus
from app.scheduling.engine import (
    ALLOWED_EXECUTION_TRANSITIONS,
    ALLOWED_JOB_TRANSITIONS,
    TriggerInput,
    calendar_rule_to_cron,
    compute_next_run_at,
    is_dispatch_suppressed,
    next_business_run_at,
    validate_execution_transition,
    validate_job_transition,
)

_NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


class TestJobTransitions:
    def test_registered_can_move_to_active(self) -> None:
        validate_job_transition(ScheduledJobStatus.REGISTERED, ScheduledJobStatus.ACTIVE)

    def test_active_can_pause(self) -> None:
        validate_job_transition(ScheduledJobStatus.ACTIVE, ScheduledJobStatus.PAUSED)

    def test_paused_can_resume(self) -> None:
        validate_job_transition(ScheduledJobStatus.PAUSED, ScheduledJobStatus.ACTIVE)

    def test_deleted_is_a_dead_end(self) -> None:
        with pytest.raises(ValidationError):
            validate_job_transition(ScheduledJobStatus.DELETED, ScheduledJobStatus.ACTIVE)

    def test_registered_cannot_pause_directly(self) -> None:
        with pytest.raises(ValidationError):
            validate_job_transition(ScheduledJobStatus.REGISTERED, ScheduledJobStatus.PAUSED)

    def test_every_status_has_a_defined_transition_set(self) -> None:
        assert set(ALLOWED_JOB_TRANSITIONS) == set(ScheduledJobStatus)


class TestExecutionTransitions:
    def test_queued_can_start_running(self) -> None:
        validate_execution_transition(ExecutionStatus.QUEUED, ExecutionStatus.RUNNING)

    def test_running_can_complete(self) -> None:
        validate_execution_transition(ExecutionStatus.RUNNING, ExecutionStatus.COMPLETED)

    def test_completed_is_a_dead_end(self) -> None:
        with pytest.raises(ValidationError):
            validate_execution_transition(ExecutionStatus.COMPLETED, ExecutionStatus.RUNNING)

    def test_failed_can_be_recovered(self) -> None:
        validate_execution_transition(ExecutionStatus.FAILED, ExecutionStatus.RECOVERED)

    def test_failed_cannot_go_straight_to_completed(self) -> None:
        with pytest.raises(ValidationError):
            validate_execution_transition(ExecutionStatus.FAILED, ExecutionStatus.COMPLETED)

    def test_every_status_has_a_defined_transition_set(self) -> None:
        assert set(ALLOWED_EXECUTION_TRANSITIONS) == set(ExecutionStatus)


class TestCalendarRuleToCron:
    def test_daily_uses_hour_and_minute(self) -> None:
        assert calendar_rule_to_cron(CalendarRuleKind.DAILY, {"hour": 2, "minute": 30}) == (
            "30 2 * * *"
        )

    def test_daily_defaults_to_midnight(self) -> None:
        assert calendar_rule_to_cron(CalendarRuleKind.DAILY, {}) == "0 0 * * *"

    def test_weekly_uses_weekday(self) -> None:
        assert (
            calendar_rule_to_cron(CalendarRuleKind.WEEKLY, {"hour": 9, "minute": 0, "weekday": 3})
            == "0 9 * * 3"
        )

    def test_weekly_defaults_to_monday(self) -> None:
        assert calendar_rule_to_cron(CalendarRuleKind.WEEKLY, {}) == "0 0 * * 1"

    def test_monthly_uses_day_of_month(self) -> None:
        assert calendar_rule_to_cron(CalendarRuleKind.MONTHLY, {"day_of_month": 15}) == (
            "0 0 15 * *"
        )

    def test_quarterly_fires_on_quarter_start_months(self) -> None:
        assert calendar_rule_to_cron(CalendarRuleKind.QUARTERLY, {"day_of_month": 1}) == (
            "0 0 1 1,4,7,10 *"
        )

    def test_yearly_uses_month_and_day(self) -> None:
        assert (
            calendar_rule_to_cron(CalendarRuleKind.YEARLY, {"month": 12, "day_of_month": 25})
            == "0 0 25 12 *"
        )

    def test_business_days_is_monday_through_friday(self) -> None:
        assert calendar_rule_to_cron(CalendarRuleKind.BUSINESS_DAYS, {"hour": 8}) == ("0 8 * * 1-5")

    def test_weekends_is_saturday_and_sunday(self) -> None:
        assert calendar_rule_to_cron(CalendarRuleKind.WEEKENDS, {"hour": 10}) == "0 10 * * 0,6"

    def test_custom_uses_the_supplied_expression_verbatim(self) -> None:
        assert (
            calendar_rule_to_cron(CalendarRuleKind.CUSTOM, {"cron_expression": "*/5 * * * *"})
            == "*/5 * * * *"
        )

    def test_custom_without_an_expression_raises(self) -> None:
        with pytest.raises(ValidationError):
            calendar_rule_to_cron(CalendarRuleKind.CUSTOM, {})

    def test_none_has_no_cron_form(self) -> None:
        with pytest.raises(ValidationError):
            calendar_rule_to_cron(CalendarRuleKind.NONE, {})


class TestComputeNextRunAt:
    def test_cron_trigger_computes_the_next_fire_time(self) -> None:
        trigger = TriggerInput(trigger_type="cron", cron_expression="0 2 * * *")
        result = compute_next_run_at(trigger, now=_NOW)
        assert result == datetime(2026, 8, 5, 2, 0, tzinfo=UTC)

    def test_interval_trigger_adds_the_interval(self) -> None:
        trigger = TriggerInput(trigger_type="interval", interval_seconds=3_600)
        result = compute_next_run_at(trigger, now=_NOW)
        assert result == datetime(2026, 8, 4, 13, 0, tzinfo=UTC)

    def test_one_time_trigger_fires_once_at_run_at(self) -> None:
        run_at = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
        trigger = TriggerInput(trigger_type="one_time", run_at=run_at)
        assert compute_next_run_at(trigger, now=_NOW) == run_at

    def test_one_time_trigger_never_fires_again_once_it_has_run(self) -> None:
        run_at = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
        trigger = TriggerInput(trigger_type="one_time", run_at=run_at)
        assert compute_next_run_at(trigger, now=_NOW, last_run=run_at) is None

    def test_manual_trigger_never_computes_a_next_run(self) -> None:
        trigger = TriggerInput(trigger_type="manual_trigger")
        assert compute_next_run_at(trigger, now=_NOW) is None

    def test_dependency_driven_trigger_never_computes_a_next_run(self) -> None:
        trigger = TriggerInput(trigger_type="dependency_driven")
        assert compute_next_run_at(trigger, now=_NOW) is None

    def test_event_driven_trigger_never_computes_a_next_run(self) -> None:
        trigger = TriggerInput(trigger_type="event_driven", cron_expression=None)
        assert compute_next_run_at(trigger, now=_NOW) is None

    def test_calendar_trigger_computes_via_the_translated_cron_expression(self) -> None:
        trigger = TriggerInput(
            trigger_type="calendar",
            calendar_rule=CalendarRuleKind.DAILY,
            calendar_config={"hour": 2, "minute": 0},
        )
        result = compute_next_run_at(trigger, now=_NOW)
        assert result == datetime(2026, 8, 5, 2, 0, tzinfo=UTC)

    def test_calendar_trigger_without_a_rule_raises(self) -> None:
        trigger = TriggerInput(trigger_type="calendar")
        with pytest.raises(ValidationError):
            compute_next_run_at(trigger, now=_NOW)

    def test_maintenance_window_trigger_never_computes_a_next_run(self) -> None:
        trigger = TriggerInput(trigger_type="maintenance_window")
        assert compute_next_run_at(trigger, now=_NOW) is None

    def test_custom_schedule_trigger_uses_its_own_cron_expression(self) -> None:
        trigger = TriggerInput(
            trigger_type="custom_schedule",
            calendar_rule=CalendarRuleKind.CUSTOM,
            calendar_config={"cron_expression": "*/15 * * * *"},
        )
        result = compute_next_run_at(trigger, now=_NOW)
        assert result is not None

    def test_unrecognised_trigger_type_raises(self) -> None:
        trigger = TriggerInput(trigger_type="not_a_real_type")
        with pytest.raises(ValidationError):
            compute_next_run_at(trigger, now=_NOW)

    def test_cron_trigger_missing_its_expression_raises(self) -> None:
        trigger = TriggerInput(trigger_type="cron", cron_expression=None)
        with pytest.raises(ValidationError):
            compute_next_run_at(trigger, now=_NOW)

    def test_invalid_cron_expression_raises_validation_error(self) -> None:
        trigger = TriggerInput(trigger_type="cron", cron_expression="not a cron expression")
        with pytest.raises(ValidationError):
            compute_next_run_at(trigger, now=_NOW)


class TestNextBusinessRunAt:
    def test_skips_a_configured_holiday(self) -> None:
        holidays = frozenset({date(2026, 8, 5)})
        result = next_business_run_at("0 2 * * *", now=_NOW, holidays=holidays)
        assert result.date() == date(2026, 8, 6)

    def test_returns_the_plain_next_run_when_no_holiday_is_in_the_way(self) -> None:
        result = next_business_run_at("0 2 * * *", now=_NOW, holidays=frozenset())
        assert result.date() == date(2026, 8, 5)

    def test_skips_multiple_consecutive_holidays(self) -> None:
        holidays = frozenset({date(2026, 8, 5), date(2026, 8, 6)})
        result = next_business_run_at("0 2 * * *", now=_NOW, holidays=holidays)
        assert result.date() == date(2026, 8, 7)

    def test_invalid_cron_expression_raises(self) -> None:
        with pytest.raises(ValidationError):
            next_business_run_at("garbage", now=_NOW, holidays=frozenset())


class TestIsDispatchSuppressed:
    def test_no_active_windows_never_suppresses(self) -> None:
        assert (
            is_dispatch_suppressed(priority=JobPriority.LOW, active_window_allows_override={})
            is False
        )

    def test_an_active_window_suppresses_a_normal_priority_job(self) -> None:
        assert (
            is_dispatch_suppressed(
                priority=JobPriority.NORMAL, active_window_allows_override={"w1": True}
            )
            is True
        )

    def test_a_critical_job_dispatches_through_an_overriding_window(self) -> None:
        assert (
            is_dispatch_suppressed(
                priority=JobPriority.CRITICAL, active_window_allows_override={"w1": True}
            )
            is False
        )

    def test_a_critical_job_is_still_suppressed_by_a_non_overriding_window(self) -> None:
        assert (
            is_dispatch_suppressed(
                priority=JobPriority.CRITICAL, active_window_allows_override={"w1": False}
            )
            is True
        )

    def test_every_active_window_must_allow_override_for_a_critical_job_to_dispatch(self) -> None:
        assert (
            is_dispatch_suppressed(
                priority=JobPriority.CRITICAL,
                active_window_allows_override={"w1": True, "w2": False},
            )
            is True
        )
