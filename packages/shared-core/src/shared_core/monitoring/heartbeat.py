"""Heartbeat.

Per docs/023_Enterprise_Monitoring_Framework.md.txt "HEARTBEAT": "Every
service shall publish heartbeat." Contains Service Name, Version,
Hostname, Environment, Timestamp, Status, CPU, Memory, Latency, Request
Count, Error Count.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from datetime import UTC, datetime

from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring.application import ApplicationStatistics, capture_application_snapshot


@dataclass(frozen=True, slots=True)
class Heartbeat:
    """One heartbeat emission, per docs/023 "HEARTBEAT"."""

    service_name: str
    version: str
    hostname: str
    environment: str
    timestamp: datetime
    status: HealthStatus
    cpu_percent: float
    memory_percent: float
    latency_ms: float
    request_count: int
    error_count: int


def build_heartbeat(
    *,
    service_name: str,
    version: str,
    environment: str,
    status: HealthStatus,
    statistics: ApplicationStatistics,
    hostname: str | None = None,
) -> Heartbeat:
    """Build a heartbeat from the current process's own application statistics and snapshot."""
    snapshot = capture_application_snapshot()
    return Heartbeat(
        service_name=service_name,
        version=version,
        hostname=hostname or socket.gethostname(),
        environment=environment,
        timestamp=datetime.now(UTC),
        status=status,
        cpu_percent=snapshot.cpu_percent,
        memory_percent=snapshot.memory_percent,
        latency_ms=statistics.average_response_time_ms,
        request_count=statistics.request_count,
        error_count=statistics.error_count,
    )


__all__ = ["Heartbeat", "build_heartbeat"]
