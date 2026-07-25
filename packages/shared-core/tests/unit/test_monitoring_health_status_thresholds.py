"""Tests for status.py, thresholds.py, exceptions.py, and health.py's Prompt 023 additions."""

from __future__ import annotations

import asyncio

import pytest
from shared_core.enums.health_status import HealthStatus
from shared_core.exceptions.monitoring import MonitoringError
from shared_core.monitoring.exceptions import (
    AlertDispatchError,
    DependencyUnavailableError,
    HealthCheckFailedError,
    RegistrationError,
    ThresholdEvaluationError,
)
from shared_core.monitoring.health import (
    CachedHealthCheck,
    DeepHealthChecker,
    StartupGate,
    liveness,
)
from shared_core.monitoring.status import calculate_status
from shared_core.monitoring.thresholds import (
    Threshold,
    ThresholdLevel,
    default_cpu_threshold,
    default_disk_threshold,
    default_memory_threshold,
)

# --- status.py ---


def test_calculate_status_picks_the_single_worst_status() -> None:
    result = calculate_status([HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.HEALTHY])

    assert result == HealthStatus.DEGRADED


def test_calculate_status_unhealthy_outranks_degraded_and_warning() -> None:
    result = calculate_status([HealthStatus.WARNING, HealthStatus.UNHEALTHY, HealthStatus.DEGRADED])

    assert result == HealthStatus.UNHEALTHY


def test_calculate_status_maintenance_mode_always_wins() -> None:
    result = calculate_status([HealthStatus.HEALTHY], maintenance_mode=True)

    assert result == HealthStatus.MAINTENANCE


def test_calculate_status_maintenance_mode_wins_over_unhealthy() -> None:
    result = calculate_status([HealthStatus.UNHEALTHY], maintenance_mode=True)

    assert result == HealthStatus.MAINTENANCE


def test_calculate_status_with_no_statuses_and_no_maintenance_is_unknown() -> None:
    assert calculate_status([]) == HealthStatus.UNKNOWN


def test_calculate_status_single_healthy_status_is_healthy() -> None:
    assert calculate_status([HealthStatus.HEALTHY]) == HealthStatus.HEALTHY


# --- thresholds.py ---


def test_threshold_evaluate_returns_the_highest_severity_breached() -> None:
    threshold = Threshold(metric_name="cpu_percent", high=75.0, critical=90.0)

    assert threshold.evaluate(95.0) == ThresholdLevel.CRITICAL
    assert threshold.evaluate(80.0) == ThresholdLevel.HIGH
    assert threshold.evaluate(50.0) is None


def test_threshold_evaluate_at_exact_boundary_breaches() -> None:
    threshold = Threshold(metric_name="cpu_percent", high=75.0)

    assert threshold.evaluate(75.0) == ThresholdLevel.HIGH


def test_threshold_evaluate_with_no_levels_configured_never_breaches() -> None:
    threshold = Threshold(metric_name="unconfigured")

    assert threshold.evaluate(1_000_000.0) is None


def test_default_cpu_threshold_has_the_expected_metric_name_and_levels() -> None:
    threshold = default_cpu_threshold()

    assert threshold.metric_name == "cpu_percent"
    assert threshold.high == pytest.approx(75.0)
    assert threshold.critical == pytest.approx(90.0)


def test_default_memory_threshold_has_the_expected_metric_name() -> None:
    assert default_memory_threshold().metric_name == "memory_percent"


def test_default_disk_threshold_has_the_expected_metric_name() -> None:
    assert default_disk_threshold().metric_name == "disk_percent"


# --- exceptions.py ---

_MONITORING_EXCEPTION_CLASSES = [
    HealthCheckFailedError,
    DependencyUnavailableError,
    ThresholdEvaluationError,
    AlertDispatchError,
    RegistrationError,
]


@pytest.mark.parametrize("exc_cls", _MONITORING_EXCEPTION_CLASSES)
def test_every_monitoring_exception_subclasses_monitoring_error(
    exc_cls: type[MonitoringError],
) -> None:
    assert issubclass(exc_cls, MonitoringError)


@pytest.mark.parametrize("exc_cls", _MONITORING_EXCEPTION_CLASSES)
def test_every_monitoring_exception_has_a_wellformed_error_code(
    exc_cls: type[MonitoringError],
) -> None:
    assert exc_cls.error_code.startswith("AIIOS-MONITORING-")


@pytest.mark.parametrize("exc_cls", _MONITORING_EXCEPTION_CLASSES)
def test_every_monitoring_exception_has_a_nonempty_default_user_message(
    exc_cls: type[MonitoringError],
) -> None:
    assert exc_cls.default_user_message


@pytest.mark.parametrize("exc_cls", _MONITORING_EXCEPTION_CLASSES)
def test_every_monitoring_exception_is_constructible_with_just_a_message(
    exc_cls: type[MonitoringError],
) -> None:
    exc = exc_cls("boom")

    assert exc.user_message == exc_cls.default_user_message


def test_monitoring_exception_error_codes_are_unique() -> None:
    codes = [exc_cls.error_code for exc_cls in _MONITORING_EXCEPTION_CLASSES]

    assert len(codes) == len(set(codes))


# --- health.py Prompt 023 additions ---


def test_liveness_is_always_healthy() -> None:
    assert liveness() == HealthStatus.HEALTHY


def test_startup_gate_is_not_ready_until_completed() -> None:
    gate = StartupGate()

    assert gate.is_ready is False
    assert gate.completed_at is None

    gate.complete()

    assert gate.is_ready is True
    assert gate.completed_at is not None


async def test_deep_health_checker_reports_healthy_when_every_check_passes() -> None:
    checker = DeepHealthChecker()
    checker.register("round_trip", _healthy)

    result = await checker.run_all()

    assert result.status == HealthStatus.HEALTHY


async def test_deep_health_checker_reports_unhealthy_when_a_check_fails() -> None:
    checker = DeepHealthChecker()
    checker.register("round_trip", _unhealthy)

    result = await checker.run_all()

    assert result.status == HealthStatus.UNHEALTHY


async def test_deep_health_checker_treats_a_raised_exception_as_unhealthy() -> None:
    async def _raises() -> HealthStatus:
        raise RuntimeError("boom")

    checker = DeepHealthChecker()
    checker.register("flaky", _raises)

    result = await checker.run_all()

    assert result.status == HealthStatus.UNHEALTHY


async def test_cached_health_check_reuses_the_cached_result_within_the_window() -> None:
    call_count = 0

    async def _counting_check() -> HealthStatus:
        nonlocal call_count
        call_count += 1
        return HealthStatus.HEALTHY

    cached = CachedHealthCheck(check=_counting_check, cache_seconds=60.0)

    await cached.get()
    await cached.get()
    await cached.get()

    assert call_count == 1


async def test_cached_health_check_rechecks_after_the_cache_expires() -> None:
    call_count = 0

    async def _counting_check() -> HealthStatus:
        nonlocal call_count
        call_count += 1
        return HealthStatus.HEALTHY

    cached = CachedHealthCheck(check=_counting_check, cache_seconds=0.01)

    await cached.get()
    await asyncio.sleep(0.05)
    await cached.get()

    assert call_count == 2


async def _healthy() -> HealthStatus:
    return HealthStatus.HEALTHY


async def _unhealthy() -> HealthStatus:
    return HealthStatus.UNHEALTHY
