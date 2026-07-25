"""Telemetry subsystem health.

Per docs/024_Enterprise_Telemetry_Framework.md.txt "HEALTH": Exporter
Status, Dropped Spans, Sampling Rate, Buffer Usage, Queue Length, Export
Latency, Telemetry Service Health. This is telemetry's own self-check --
distinct from, and not registered with,
:mod:`shared_core.monitoring.checks` (which doesn't know about this
framework); a service can feed a :class:`TelemetryHealthReport` into its
own :mod:`shared_core.monitoring` dependency checks if it wants to.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared_core.enums.health_status import HealthStatus

_BUFFER_NEAR_FULL_RATIO: float = 0.9


@dataclass(frozen=True, slots=True)
class TelemetryHealthReport:
    """A point-in-time snapshot of the telemetry subsystem's own health."""

    status: HealthStatus
    exporter_healthy: bool
    dropped_spans: int
    sampling_rate: float
    buffer_usage: int
    buffer_capacity: int
    queue_length: int
    export_latency_ms: float | None


def calculate_telemetry_health(
    *,
    exporter_healthy: bool,
    dropped_spans: int,
    sampling_rate: float,
    buffer_usage: int,
    buffer_capacity: int,
    queue_length: int,
    export_latency_ms: float | None,
) -> TelemetryHealthReport:
    """Build a :class:`TelemetryHealthReport`, deriving overall status from its inputs.

    ``UNHEALTHY`` if the exporter itself is failing; ``DEGRADED`` if
    spans are being dropped or the buffer is nearly full (still
    exporting, just under pressure); ``HEALTHY`` otherwise.
    """
    if not exporter_healthy:
        status = HealthStatus.UNHEALTHY
    elif dropped_spans > 0 or (
        buffer_capacity > 0 and buffer_usage / buffer_capacity >= _BUFFER_NEAR_FULL_RATIO
    ):
        status = HealthStatus.DEGRADED
    else:
        status = HealthStatus.HEALTHY
    return TelemetryHealthReport(
        status=status,
        exporter_healthy=exporter_healthy,
        dropped_spans=dropped_spans,
        sampling_rate=sampling_rate,
        buffer_usage=buffer_usage,
        buffer_capacity=buffer_capacity,
        queue_length=queue_length,
        export_latency_ms=export_latency_ms,
    )


__all__ = ["TelemetryHealthReport", "calculate_telemetry_health"]
