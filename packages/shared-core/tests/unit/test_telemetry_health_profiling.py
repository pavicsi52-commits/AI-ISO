"""Tests for health.py and profiling.py."""

from __future__ import annotations

import time

from shared_core.enums.health_status import HealthStatus
from shared_core.telemetry.health import calculate_telemetry_health
from shared_core.telemetry.profiling import DeepProfile, measure_duration_ms

# --- health.py ---


def _healthy_kwargs() -> dict[str, object]:
    return {
        "exporter_healthy": True,
        "dropped_spans": 0,
        "sampling_rate": 1.0,
        "buffer_usage": 10,
        "buffer_capacity": 100,
        "queue_length": 0,
        "export_latency_ms": 5.0,
    }


def test_calculate_telemetry_health_is_healthy_when_everything_is_fine() -> None:
    report = calculate_telemetry_health(**_healthy_kwargs())  # type: ignore[arg-type]

    assert report.status == HealthStatus.HEALTHY


def test_calculate_telemetry_health_is_unhealthy_when_the_exporter_is_down() -> None:
    kwargs = _healthy_kwargs()
    kwargs["exporter_healthy"] = False

    report = calculate_telemetry_health(**kwargs)  # type: ignore[arg-type]

    assert report.status == HealthStatus.UNHEALTHY


def test_calculate_telemetry_health_is_degraded_when_spans_are_dropped() -> None:
    kwargs = _healthy_kwargs()
    kwargs["dropped_spans"] = 5

    report = calculate_telemetry_health(**kwargs)  # type: ignore[arg-type]

    assert report.status == HealthStatus.DEGRADED


def test_calculate_telemetry_health_is_degraded_when_buffer_is_nearly_full() -> None:
    kwargs = _healthy_kwargs()
    kwargs["buffer_usage"] = 95
    kwargs["buffer_capacity"] = 100

    report = calculate_telemetry_health(**kwargs)  # type: ignore[arg-type]

    assert report.status == HealthStatus.DEGRADED


def test_calculate_telemetry_health_tolerates_a_zero_buffer_capacity() -> None:
    kwargs = _healthy_kwargs()
    kwargs["buffer_capacity"] = 0

    report = calculate_telemetry_health(**kwargs)  # type: ignore[arg-type]

    assert report.status == HealthStatus.HEALTHY


# --- profiling.py ---


def test_measure_duration_ms_times_a_block() -> None:
    with measure_duration_ms("sleep") as result:
        time.sleep(0.02)

    assert result.label == "sleep"
    assert result.duration_ms >= 15.0


def test_deep_profile_captures_stats_for_the_wrapped_block() -> None:
    with DeepProfile() as profile:

        def _work() -> int:
            return sum(range(10_000))

        _work()

    stats = profile.stats(top_n=5)

    assert "_work" in stats
