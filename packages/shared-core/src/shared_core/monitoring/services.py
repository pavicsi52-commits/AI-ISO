"""Service health registry.

Per docs/023_Enterprise_Monitoring_Framework.md.txt "SERVICE HEALTH" /
"MONITORING CATEGORIES": tracks the reported health of *other* AI-IOS
microservices (peer services) -- distinct from
:mod:`shared_core.monitoring.dependencies`, which tracks the
infrastructure (databases, brokers, external APIs) *this* service
itself depends on.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring.status import calculate_status


@dataclass(frozen=True, slots=True)
class ServiceHealth:
    """The last-known health of one peer service."""

    name: str
    status: HealthStatus
    reported_at: float
    version: str | None = None


@dataclass(slots=True)
class ServiceRegistry:
    """Tracks the last-reported health of every known peer service."""

    _services: dict[str, ServiceHealth] = field(default_factory=dict)

    def report(self, name: str, status: HealthStatus, *, version: str | None = None) -> None:
        """Record a peer service's self-reported health (e.g. from its own heartbeat)."""
        self._services[name] = ServiceHealth(
            name=name, status=status, reported_at=time.monotonic(), version=version
        )

    def get(self, name: str) -> ServiceHealth | None:
        """Return the last-known health of *name*, or ``None`` if it has never reported."""
        return self._services.get(name)

    def all(self) -> list[ServiceHealth]:
        """Return every known peer service's last-reported health."""
        return list(self._services.values())

    def overall_status(self) -> HealthStatus:
        """Calculate the worst-case status across every known peer service.

        ``HEALTHY`` if no peer service has ever reported -- consistent
        with :class:`~shared_core.monitoring.health.HealthChecker`'s own
        "no registered checks is healthy" convention, rather than
        :func:`~shared_core.monitoring.status.calculate_status`'s generic
        "no statuses to report from" ``UNKNOWN`` default.
        """
        if not self._services:
            return HealthStatus.HEALTHY
        return calculate_status(service.status for service in self._services.values())

    def stale_services(self, *, max_age_seconds: float) -> list[ServiceHealth]:
        """Return every service last reported over *max_age_seconds* ago (a missed heartbeat)."""
        now = time.monotonic()
        return [
            service
            for service in self._services.values()
            if now - service.reported_at > max_age_seconds
        ]


__all__ = ["ServiceHealth", "ServiceRegistry"]
