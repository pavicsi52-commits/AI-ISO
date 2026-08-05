"""Health probing and circuit breaking.

Thin adapter onto `shared_core.monitoring.checks.check_http_reachable`
(the health probe) and `shared_core.connectors.retry.CircuitBreaker`
(the three-state breaker) -- both already exist and are reused
directly, per this prompt's own "use every previously implemented
platform framework" instruction and this prompt's own research phase
confirming they exist.
"""

from __future__ import annotations

from shared_core.connectors.retry import CircuitBreaker
from shared_core.monitoring.checks import DependencyCheckResult, check_http_reachable

from app.models.enums import HealthState, from_shared_health_status


async def probe_instance(name: str, url: str, *, timeout_seconds: float) -> DependencyCheckResult:
    """Probe one backend instance's own health."""
    return await check_http_reachable(name, url, timeout_seconds=timeout_seconds)


def health_state_from_probe(result: DependencyCheckResult) -> HealthState:
    """Convert a probe's own `shared_core` health status into this service's own vocabulary."""
    return from_shared_health_status(result.status)


def build_circuit_breaker(*, failure_threshold: int, recovery_seconds: float) -> CircuitBreaker:
    """Build one circuit breaker for one backend instance."""
    return CircuitBreaker(failure_threshold=failure_threshold, recovery_seconds=recovery_seconds)


__all__ = ["build_circuit_breaker", "health_state_from_probe", "probe_instance"]
