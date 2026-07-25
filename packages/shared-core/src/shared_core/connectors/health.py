"""Connector health.

Per docs/027_Enterprise_Connector_SDK.md.txt "HEALTH": Connection
Status, Latency, Availability, Authentication Status, Protocol Status,
Provider Status. Reuses
:func:`shared_core.monitoring.status.calculate_status` (Prompt 023,
already implements worst-case status rollup) rather than a second
status calculation. "Provider Status" is this report's own overall
``status`` -- there is no separate per-provider dimension beyond the
worst case of connection/authentication/protocol.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared_core.connectors.connection import ConnectionState
from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring.status import calculate_status

_CONNECTION_STATE_HEALTH: dict[ConnectionState, HealthStatus] = {
    ConnectionState.CONNECTED: HealthStatus.HEALTHY,
    ConnectionState.CONNECTING: HealthStatus.DEGRADED,
    ConnectionState.RECONNECTING: HealthStatus.DEGRADED,
    ConnectionState.DISCONNECTED: HealthStatus.UNKNOWN,
    ConnectionState.FAILED: HealthStatus.UNHEALTHY,
}


@dataclass(frozen=True, slots=True)
class ConnectorHealthReport:
    """A point-in-time snapshot of one connector instance's health."""

    status: HealthStatus
    connection_status: HealthStatus
    authentication_status: HealthStatus
    protocol_status: HealthStatus
    latency_ms: float | None = None
    availability_percent: float | None = None
    error: str | None = None


def connection_state_to_health(state: ConnectionState) -> HealthStatus:
    """Map a :class:`ConnectionState` onto the closest :class:`HealthStatus`."""
    return _CONNECTION_STATE_HEALTH[state]


def build_health_report(
    *,
    connection_state: ConnectionState,
    authenticated: bool,
    protocol_ok: bool,
    latency_ms: float | None = None,
    availability_percent: float | None = None,
    error: str | None = None,
) -> ConnectorHealthReport:
    """Build a :class:`ConnectorHealthReport` from the signals every connector already tracks."""
    connection_status = connection_state_to_health(connection_state)
    authentication_status = HealthStatus.HEALTHY if authenticated else HealthStatus.UNHEALTHY
    protocol_status = HealthStatus.HEALTHY if protocol_ok else HealthStatus.UNHEALTHY
    overall = calculate_status([connection_status, authentication_status, protocol_status])
    return ConnectorHealthReport(
        status=overall,
        connection_status=connection_status,
        authentication_status=authentication_status,
        protocol_status=protocol_status,
        latency_ms=latency_ms,
        availability_percent=availability_percent,
        error=error,
    )


__all__ = ["ConnectorHealthReport", "build_health_report", "connection_state_to_health"]
