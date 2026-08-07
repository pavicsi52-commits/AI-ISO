"""Connector health monitoring (docs/058 "HEALTH MANAGEMENT").

Reuses the same `shared_core.monitoring.checks` primitives
`app/services/connection.py` uses for on-demand testing -- this
service's own periodic probe and a caller-triggered "test connection"
answer the same underlying question (can this connector's own endpoint
currently be reached?), just on two different triggers (a leader-elected
sweep here, an explicit API call there) and writing to two different
tables (`connector_health` vs `connector_connections`) per docs/058's
own "DATABASE TABLES" split.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring.checks import check_http_reachable, check_tcp_reachable

from app.models.connector import Connector
from app.models.health import ConnectorHealth
from app.repositories.health import ConnectorHealthRepository


class HealthService:
    """Runs and records one automated health probe for a connector."""

    def __init__(
        self,
        health: ConnectorHealthRepository,
        *,
        timeout_seconds: float = 5.0,
        failure_threshold: int = 3,
    ) -> None:
        self._health = health
        self._timeout_seconds = timeout_seconds
        self._failure_threshold = failure_threshold

    async def probe(self, connector: Connector) -> ConnectorHealth:
        """Probe *connector*'s own configured endpoint and record the outcome.

        ``recovery_attempted`` is set once *connector*'s own
        ``consecutive_failures`` (updated by the caller via
        ``ConnectorService.record_health_outcome`` after this call)
        reaches ``failure_threshold`` -- docs/058's own "Automatic
        Recovery" is satisfied by publishing a ``ConnectorHealthChanged``
        event at that point for another platform component (e.g.
        automation-service) to react to, not by this service itself
        reaching into a third-party system it has no live client for.
        """
        status, latency_ms, error = await self._probe_endpoint(connector)
        recovery_attempted = (
            status != HealthStatus.HEALTHY
            and connector.consecutive_failures + 1 >= self._failure_threshold
        )
        return await self._health.create(
            ConnectorHealth(
                organization_id=connector.organization_id,
                connector_id=connector.id,
                status=status,
                latency_ms=latency_ms,
                checked_at=datetime.now(UTC),
                error=error,
                consecutive_failures=(
                    0 if status == HealthStatus.HEALTHY else connector.consecutive_failures + 1
                ),
                recovery_attempted=recovery_attempted,
            )
        )

    async def _probe_endpoint(
        self, connector: Connector
    ) -> tuple[HealthStatus, float | None, str | None]:
        endpoint_url = connector.config.get("endpoint_url")
        host = connector.config.get("host")
        port = connector.config.get("port")

        if isinstance(endpoint_url, str) and endpoint_url:
            result = await check_http_reachable(
                connector.name, endpoint_url, timeout_seconds=self._timeout_seconds
            )
            return result.status, result.latency_ms, result.error
        if isinstance(host, str) and host and isinstance(port, int):
            result = await check_tcp_reachable(
                connector.name, host, port, timeout_seconds=self._timeout_seconds
            )
            return result.status, result.latency_ms, result.error
        return HealthStatus.UNKNOWN, None, "No checkable endpoint_url or host/port configured."

    async def list_for_connector(
        self, connector_id: UUID, *, limit: int = 50
    ) -> list[ConnectorHealth]:
        """Recent health checks for one connector, newest first."""
        return await self._health.list_for_connector(connector_id, limit=limit)

    async def latest_for_connector(self, connector_id: UUID) -> ConnectorHealth | None:
        """The most recent health check for one connector, if any."""
        return await self._health.latest_for_connector(connector_id)


__all__ = ["HealthService"]
