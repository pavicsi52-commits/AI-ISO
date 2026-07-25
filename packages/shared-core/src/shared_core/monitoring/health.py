"""Health check framework.

Per docs/023_Enterprise_Monitoring_Framework.md.txt "HEALTH CHECKS":
Liveness, Readiness, Startup, Dependency, Deep Health, Custom Health
Checks, Periodic Health Checks.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring.constants import DEFAULT_HEALTH_CHECK_CACHE_SECONDS
from shared_core.responses.health import DependencyCheck, ReadinessResponse

DependencyCheckFn = Callable[[], Awaitable[HealthStatus]]


class HealthChecker:
    """Registry of named dependency health checks, run together on demand.

    The Prompt 012 baseline, unchanged -- it already covers "Dependency"
    and "Custom Health Checks" by itself.
    """

    def __init__(self) -> None:
        self._checks: dict[str, DependencyCheckFn] = {}

    def register(self, name: str, check: DependencyCheckFn) -> None:
        """Register a named async dependency check."""
        self._checks[name] = check

    async def run_all(self) -> ReadinessResponse:
        """Run every registered check and aggregate the results ("Readiness").

        Overall status is ``HEALTHY`` only if every dependency reports
        ``HEALTHY``; ``UNHEALTHY`` if any dependency does.
        """
        results: list[DependencyCheck] = []
        for name, check in self._checks.items():
            try:
                status = await check()
            except Exception:
                status = HealthStatus.UNHEALTHY
            results.append(DependencyCheck(name=name, status=status))

        overall = (
            HealthStatus.HEALTHY
            if all(check.status == HealthStatus.HEALTHY for check in results)
            else HealthStatus.UNHEALTHY
        )
        return ReadinessResponse(status=overall, checks=results)


def liveness() -> HealthStatus:
    """Return whether this process is alive at all ("Liveness").

    Trivially ``HEALTHY`` -- if this function can run, the process is
    alive by definition. Distinct from readiness (whether dependencies
    are reachable) and deep health (whether the service is actually
    *working*): liveness answers only "should this process be restarted?"
    """
    return HealthStatus.HEALTHY


@dataclass(slots=True)
class StartupGate:
    """Tracks whether the service has completed its one-time startup checks ("Startup").

    A service typically has work to do exactly once before serving
    traffic (initial migrations applied, caches warmed) and calls
    :meth:`complete` when done; readiness/liveness probes can check
    :attr:`is_ready` to hold traffic until startup finishes.
    """

    _is_ready: bool = False
    _completed_at: float | None = None

    def complete(self) -> None:
        """Mark startup as complete."""
        self._is_ready = True
        self._completed_at = time.monotonic()

    @property
    def is_ready(self) -> bool:
        """Whether startup has completed."""
        return self._is_ready

    @property
    def completed_at(self) -> float | None:
        """The :func:`time.monotonic` timestamp startup completed at, or ``None`` if not yet."""
        return self._completed_at


DeepHealthCheckFn = Callable[[], Awaitable[HealthStatus]]


class DeepHealthChecker:
    """Registry of "Deep Health" checks -- more thorough than a basic readiness ping.

    Where :class:`HealthChecker`'s checks typically confirm a dependency
    is *reachable* (a ping), a deep check confirms the service is
    actually *working end-to-end* (e.g. a real read-then-write round
    trip) -- more expensive, so pair it with :class:`CachedHealthCheck`
    below rather than running it on every request.
    """

    def __init__(self) -> None:
        self._checks: dict[str, DeepHealthCheckFn] = {}

    def register(self, name: str, check: DeepHealthCheckFn) -> None:
        """Register a named deep health check."""
        self._checks[name] = check

    async def run_all(self) -> ReadinessResponse:
        """Run every registered deep check and aggregate the results."""
        results: list[DependencyCheck] = []
        for name, check in self._checks.items():
            try:
                status = await check()
            except Exception:
                status = HealthStatus.UNHEALTHY
            results.append(DependencyCheck(name=name, status=status))
        overall = (
            HealthStatus.HEALTHY
            if all(check.status == HealthStatus.HEALTHY for check in results)
            else HealthStatus.UNHEALTHY
        )
        return ReadinessResponse(status=overall, checks=results)


@dataclass(slots=True)
class CachedHealthCheck:
    """Wraps an expensive check with a short-lived cache ("Periodic Health Checks").

    Repeated readiness probes (e.g. a Kubernetes probe hitting the
    endpoint every few seconds) shouldn't each re-run every dependency
    check from scratch -- this returns the last result if it's still
    within *cache_seconds*, and only re-runs the check once that expires.
    """

    check: Callable[[], Awaitable[HealthStatus]]
    cache_seconds: float = DEFAULT_HEALTH_CHECK_CACHE_SECONDS
    _cached_status: HealthStatus | None = field(default=None, init=False)
    _cached_at: float = field(default=0.0, init=False)

    async def get(self) -> HealthStatus:
        """Return the cached status if still fresh, otherwise re-run the check."""
        now = time.monotonic()
        if self._cached_status is not None and (now - self._cached_at) < self.cache_seconds:
            return self._cached_status
        status = await self.check()
        self._cached_status = status
        self._cached_at = now
        return status


__all__ = [
    "CachedHealthCheck",
    "DeepHealthChecker",
    "DependencyCheckFn",
    "HealthChecker",
    "StartupGate",
    "liveness",
]
