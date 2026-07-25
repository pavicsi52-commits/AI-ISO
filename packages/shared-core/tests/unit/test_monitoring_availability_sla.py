"""Tests for availability.py and sla.py."""

from __future__ import annotations

import time

import pytest
from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring.application import ApplicationStatistics
from shared_core.monitoring.availability import AvailabilityTracker
from shared_core.monitoring.sla import ServiceLevelObjective, build_sla_report

# --- availability.py ---


def test_availability_window_percentage_is_a_hundred_with_no_elapsed_time() -> None:
    tracker = AvailabilityTracker()

    assert tracker.current_window().percentage == 100.0


def test_availability_window_percentage_is_a_hundred_with_no_downtime() -> None:
    tracker = AvailabilityTracker()
    tracker.record(HealthStatus.HEALTHY)
    time.sleep(0.03)

    assert tracker.availability_percentage == pytest.approx(100.0, abs=0.5)


def test_availability_tracker_records_downtime_after_an_unhealthy_transition() -> None:
    tracker = AvailabilityTracker()
    tracker.record(HealthStatus.HEALTHY)
    time.sleep(0.03)
    tracker.record(HealthStatus.UNHEALTHY)
    time.sleep(0.03)
    # A second transition *out of* UNHEALTHY closes out its down_seconds tally too.
    tracker.record(HealthStatus.HEALTHY)

    window = tracker.current_window()

    assert window.up_seconds > 0.0
    assert window.percentage < 100.0


def test_availability_tracker_treats_degraded_and_warning_as_up() -> None:
    tracker = AvailabilityTracker()
    tracker.record(HealthStatus.DEGRADED)
    time.sleep(0.02)
    tracker.record(HealthStatus.WARNING)
    time.sleep(0.02)

    window = tracker.current_window()

    assert window.up_seconds == pytest.approx(window.total_seconds, abs=0.05)


def test_availability_tracker_total_seconds_stays_zero_before_the_first_record() -> None:
    tracker = AvailabilityTracker()
    time.sleep(0.02)

    window = tracker.current_window()

    assert window.total_seconds == 0.0
    assert window.percentage == 100.0


def test_availability_tracker_total_seconds_grows_only_after_the_first_record() -> None:
    tracker = AvailabilityTracker()
    tracker.record(HealthStatus.HEALTHY)
    time.sleep(0.02)

    window = tracker.current_window()

    assert window.total_seconds > 0.0


# --- sla.py ---


def test_service_level_objective_defaults_are_populated() -> None:
    objective = ServiceLevelObjective()

    assert objective.target_availability_percent > 0.0
    assert objective.target_response_time_ms > 0.0
    assert objective.target_error_rate_percent > 0.0


def test_build_sla_report_meets_all_targets_when_everything_is_healthy() -> None:
    statistics = ApplicationStatistics()
    statistics.record_request(10.0)
    availability = AvailabilityTracker()
    availability.record(HealthStatus.HEALTHY)

    report = build_sla_report(
        objective=ServiceLevelObjective(),
        statistics=statistics,
        availability=availability,
    )

    assert report.meets_availability_target is True
    assert report.meets_response_time_target is True
    assert report.meets_error_rate_target is True
    assert report.meets_all_targets is True


def test_build_sla_report_fails_response_time_target_when_too_slow() -> None:
    statistics = ApplicationStatistics()
    statistics.record_request(999_999.0)
    availability = AvailabilityTracker()
    availability.record(HealthStatus.HEALTHY)

    report = build_sla_report(
        objective=ServiceLevelObjective(target_response_time_ms=500.0),
        statistics=statistics,
        availability=availability,
    )

    assert report.meets_response_time_target is False
    assert report.meets_all_targets is False


def test_build_sla_report_fails_error_rate_target_when_error_rate_too_high() -> None:
    statistics = ApplicationStatistics()
    for _ in range(4):
        statistics.record_request(1.0)
    statistics.record_error()
    statistics.record_error()
    availability = AvailabilityTracker()
    availability.record(HealthStatus.HEALTHY)

    report = build_sla_report(
        objective=ServiceLevelObjective(target_error_rate_percent=1.0),
        statistics=statistics,
        availability=availability,
    )

    assert report.indicators.error_rate_percent == pytest.approx(50.0)
    assert report.meets_error_rate_target is False
