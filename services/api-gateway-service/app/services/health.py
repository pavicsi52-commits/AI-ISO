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
        breakers: dict[str, CircuitBreaker] | None = None,
    ) -> None:
        self._health_repo = health_repo
        self._failure_threshold = failure_threshold
        self._recovery_seconds = recovery_seconds
        self._probe_timeout_seconds = probe_timeout_seconds
        # Shared with every other `HealthMonitorService` built against the
        # same process -- request-scoped instances come and go with each
        # session, but a circuit breaker's whole purpose is remembering
        # what *this process* has recently seen, so the dict itself must
        # outlive any one instance. The app factory owns one dict on
        # `app.state.circuit_breakers` and threads it into every instance
        # built either per-request (`app/api/deps.py`) or per-worker-tick
        # (`app/workers/health_probe_sweep.py`).
        self._breakers: dict[str, CircuitBreaker] = breakers if breakers is not None else {}

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
        # `consecutive_failures=0` is explicit, not relying on the column's
        # own default: a mapped column's default only applies at flush,
        # so a freshly constructed (not-yet-flushed) row's attribute is
        # `None` until then -- and the `+=` a few lines below needs an
        # `int` immediately, before this row is ever flushed.
        row = existing or ApiServiceHealth(
            organization_id=organization_id,
            service_id=service_id,
            instance_url=instance_url,
            consecutive_failures=0,
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

    async def list_for_org(self, organization_id: UUID) -> list[ApiServiceHealth]:
        """Every instance's own last-probed health row, across every service in this org."""
        return await self._health_repo.list_for_org(organization_id)


__all__ = ["HealthMonitorService"]
