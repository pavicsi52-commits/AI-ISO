"""Service status calculation.

Per docs/023_Enterprise_Monitoring_Framework.md.txt "SERVICE STATUS":
Healthy, Degraded, Warning, Unavailable, Maintenance, Unknown. "Status
shall be calculated automatically" -- this module is that calculation,
reusing :class:`~shared_core.enums.health_status.HealthStatus` directly
(extended in this prompt with ``WARNING``/``MAINTENANCE`` to cover all
six spec values) rather than introducing a second, parallel status enum.
"""

from __future__ import annotations

from collections.abc import Iterable

from shared_core.enums.health_status import HealthStatus

# Lower rank = worse. MAINTENANCE is a deliberate operator override, so it
# outranks even UNHEALTHY; HEALTHY only wins when nothing else applies.
_SEVERITY_RANK: dict[HealthStatus, int] = {
    HealthStatus.MAINTENANCE: 0,
    HealthStatus.UNHEALTHY: 1,
    HealthStatus.WARNING: 2,
    HealthStatus.DEGRADED: 3,
    HealthStatus.UNKNOWN: 4,
    HealthStatus.HEALTHY: 5,
}


def calculate_status(
    statuses: Iterable[HealthStatus], *, maintenance_mode: bool = False
) -> HealthStatus:
    """Calculate the single worst-case overall status from *statuses*.

    ``maintenance_mode=True`` always wins outright (an explicit operator
    override) regardless of what any individual check reports. An empty
    *statuses* with no maintenance override is ``UNKNOWN`` -- there is
    nothing to report a status from.
    """
    if maintenance_mode:
        return HealthStatus.MAINTENANCE
    resolved = list(statuses)
    if not resolved:
        return HealthStatus.UNKNOWN
    return min(resolved, key=lambda status: _SEVERITY_RANK[status])


__all__ = ["calculate_status"]
