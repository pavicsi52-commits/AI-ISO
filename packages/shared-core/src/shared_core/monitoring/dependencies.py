"""Dependency monitoring registry.

Per docs/023_Enterprise_Monitoring_Framework.md.txt "DEPENDENCY
MONITORING": "Every dependency must expose health status." Wraps
:mod:`shared_core.monitoring.checks`'s per-dependency check functions
into one named registry, run together on demand.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring.checks import DependencyCheckResult
from shared_core.monitoring.status import calculate_status

DependencyMonitorCheckFn = Callable[[], Awaitable[DependencyCheckResult]]


@dataclass(slots=True)
class DependencyMonitor:
    """Registry of named dependency health checks, run together on demand."""

    _checks: dict[str, DependencyMonitorCheckFn] = field(default_factory=dict)

    def register(self, name: str, check: DependencyMonitorCheckFn) -> None:
        """Register a named async dependency check."""
        self._checks[name] = check

    def unregister(self, name: str) -> None:
        """Remove a registered dependency check, if present."""
        self._checks.pop(name, None)

    async def check_all(self) -> list[DependencyCheckResult]:
        """Run every registered dependency check.

        A check that itself raises is reported as ``UNHEALTHY`` rather
        than propagating -- one broken dependency check must never take
        down the whole monitoring sweep.
        """
        results: list[DependencyCheckResult] = []
        for name, check in self._checks.items():
            try:
                results.append(await check())
            except Exception as exc:
                results.append(
                    DependencyCheckResult(
                        name=name, status=HealthStatus.UNHEALTHY, latency_ms=0.0, error=str(exc)
                    )
                )
        return results

    async def overall_status(self) -> HealthStatus:
        """Calculate the worst-case status across every registered dependency.

        ``HEALTHY`` if nothing is registered yet -- consistent with
        :class:`~shared_core.monitoring.health.HealthChecker`'s own "no
        registered checks is healthy" convention, rather than
        :func:`~shared_core.monitoring.status.calculate_status`'s generic
        "no statuses to report from" ``UNKNOWN`` default.
        """
        if not self._checks:
            return HealthStatus.HEALTHY
        results = await self.check_all()
        return calculate_status(result.status for result in results)


__all__ = ["DependencyMonitor", "DependencyMonitorCheckFn"]
