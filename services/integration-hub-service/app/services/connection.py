"""Connector connection testing (docs/058 "CONNECTOR LIFECYCLE": Testing).

Reuses `shared_core.monitoring.checks.check_http_reachable`/
`.check_tcp_reachable` directly -- the same generic, protocol-level
primitives `shared_core.monitoring.checks`'s own docstring says exist
precisely for a dependency with no dedicated client wrapper in this
codebase, which describes every third-party system a connector here
might point at. A connector whose own `config` declares neither an
`endpoint_url` nor a `host`/`port` pair has nothing this service can
independently reach -- its own test checks the one thing it *can*
verify honestly (that it has both configuration and an active
credential), never claims to have validated connectivity it has no way
to perform.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring.checks import check_http_reachable, check_tcp_reachable

from app.models.connector import Connector
from app.models.credential import ConnectorConnection
from app.models.enums import ConnectionStatus
from app.repositories.credential import ConnectorConnectionRepository


class ConnectionService:
    """Runs and records one discrete connect/test attempt for a connector."""

    def __init__(
        self, connections: ConnectorConnectionRepository, *, timeout_seconds: float = 5.0
    ) -> None:
        self._connections = connections
        self._timeout_seconds = timeout_seconds

    async def test(
        self,
        connector: Connector,
        *,
        credential_id: UUID | None = None,
        has_active_credential: bool,
    ) -> ConnectorConnection:
        """Attempt to reach *connector*'s own configured endpoint, and record the outcome."""
        status, latency_ms, error, metadata = await self._probe(connector, has_active_credential)
        previous = await self._connections.list_for_connector(connector.id, limit=1)
        attempt_number = (previous[0].attempt_number + 1) if previous else 1
        return await self._connections.create(
            ConnectorConnection(
                organization_id=connector.organization_id,
                connector_id=connector.id,
                credential_id=credential_id,
                status=status,
                tested_at=datetime.now(UTC),
                latency_ms=latency_ms,
                error=error,
                response_metadata=metadata,
                attempt_number=attempt_number,
            )
        )

    async def _probe(
        self, connector: Connector, has_active_credential: bool
    ) -> tuple[ConnectionStatus, float | None, str | None, dict[str, object]]:
        endpoint_url = connector.config.get("endpoint_url")
        host = connector.config.get("host")
        port = connector.config.get("port")

        if isinstance(endpoint_url, str) and endpoint_url:
            result = await check_http_reachable(
                connector.name, endpoint_url, timeout_seconds=self._timeout_seconds
            )
            status = (
                ConnectionStatus.SUCCESS
                if result.status == HealthStatus.HEALTHY
                else ConnectionStatus.FAILED
            )
            return status, result.latency_ms, result.error, {"checked": "http", "url": endpoint_url}

        if isinstance(host, str) and host and isinstance(port, int):
            result = await check_tcp_reachable(
                connector.name, host, port, timeout_seconds=self._timeout_seconds
            )
            status = (
                ConnectionStatus.SUCCESS
                if result.status == HealthStatus.HEALTHY
                else ConnectionStatus.FAILED
            )
            return (
                status,
                result.latency_ms,
                result.error,
                {"checked": "tcp", "host": host, "port": port},
            )

        if connector.config and has_active_credential:
            return ConnectionStatus.SUCCESS, None, None, {"checked": "structural"}
        missing = "configuration" if not connector.config else "an active credential"
        return (
            ConnectionStatus.FAILED,
            None,
            f"Connector has no {missing}.",
            {"checked": "structural"},
        )


__all__ = ["ConnectionService"]
