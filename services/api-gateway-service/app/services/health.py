"""Backend instance health probing and circuit breaking."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.connectors.retry import CircuitBreaker

from app.health import engine as health_engine
from app.models.enums import (
    CircuitBreakerState,
    HealthState,
    from_shared_circuit_state,
    health_state_of,
)
from app.models.health import ApiServiceHealth
from app.repositories.health import ApiServiceHealthRepository


class HealthMonitorService:
    """Probes backend instances and tracks their own circuit breaker state.

    Circuit breakers are held in-process, one per instance URL, for the
    lifetime of this service object -- a breaker's whole purpose is
    reacting to calls *this process* just made, so per-process state is
    correct here, not a shortcut. The *last probed result* is still
    persisted to ``api_health`` for cross-replica visibility and
    reporting.
    """

    def __init__(
        self,
        health_repo: ApiServiceHealthRepository,
        *,
        failure_threshold: int,
        recovery_seconds: float,
        probe_timeout_seconds: float,
    ) -> None:
        self._health_repo = health_repo
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._probe_timeout_seconds = probe_timeout_seconds
        self._breakers: dict[str, CircuitBreaker] = {}

    def breaker_for(self, instance_url: str) -> CircuitBreaker:
        """This process's own circuit breaker for one instance, creating it on first use."""
        if instance_url not in self._breakers:
            self._breakers[instance_url] = health_engine.build_circuit_breaker(
                failure_threshold=self._failure_threshold, recovery_seconds=self._recovery_seconds
            )
        return self._breakers[instance_url]

    def circuit_state(self, instance_url: str) -> CircuitBreakerState:
        """This instance's own current circuit state, without creating a breaker for it."""
        breaker = self._breakers.get(instance_url)
        if breaker is None:
            return CircuitBreakerState.CLOSED
        return from_shared_circuit_state(breaker.state)

    async def probe(
        self, organization_id: UUID, service_id: UUID, instance_url: str, *, service_name: str
    ) -> ApiServiceHealth:
        """Probe one instance and persist its own result."""
        result = await health_engine.probe_instance(
            service_name, instance_url, timeout_seconds=self._probe_timeout_seconds
        )
        state = health_engine.health_state_from_probe(result)
        existing = await self._health_repo.get_for_instance(
            organization_id, service_id, instance_url
        )
        row = existing or ApiServiceHealth(
            organization_id=organization_id, service_id=service_id, instance_url=instance_url
        )
        row.status = state
        row.latency_ms = result.latency_ms
        row.error = result.error
        row.checked_at = datetime.now(UTC)

        breaker = self.breaker_for(instance_url)
        if state == HealthState.HEALTHY:
            breaker.record_success()
            row.consecutive_failures = 0
        else:
            breaker.record_failure()
            row.consecutive_failures += 1
        row.circuit_state = from_shared_circuit_state(breaker.state)

        if existing is None:
            return await self._health_repo.create(row)
        return await self._health_repo.update(row)

    async def snapshot(self, organization_id: UUID, service_id: UUID) -> dict[str, HealthState]:
        """Every instance's own last-probed health, keyed by URL."""
        rows = await self._health_repo.list_for_service(organization_id, service_id)
        return {row.instance_url: health_state_of(row.status) for row in rows}

    async def circuit_snapshot(
        self, organization_id: UUID, service_id: UUID
    ) -> dict[str, CircuitBreakerState]:
        """Every instance's own last-persisted circuit state, keyed by URL."""
        rows = await self._health_repo.list_for_service(organization_id, service_id)
        return {row.instance_url: CircuitBreakerState(row.circuit_state) for row in rows}


__all__ = ["HealthMonitorService"]
