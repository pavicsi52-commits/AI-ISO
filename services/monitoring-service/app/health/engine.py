"""Health calculation engine -- rolls up multiple
:class:`~app.models.enums.HealthCheckType` signals for one target into
its own single overall status ("Overall Health Score"), and folds a
target's own dependency graph into a dependency-aware "blast radius"
status ("DEPENDENCY HEALTH" "Support": Topology-aware Health, Parent/
Child Health, Blast Radius Calculation). Reuses
``shared_core.monitoring.status.calculate_status`` (the platform-wide
worst-case rollup every service's own ``/readiness`` endpoint already
uses) rather than duplicating its severity ranking.
"""

from __future__ import annotations

from collections.abc import Iterable

from shared_core.enums.health_status import HealthStatus
from shared_core.monitoring.status import calculate_status

_STATUS_SCORES: dict[HealthStatus, float] = {
    HealthStatus.HEALTHY: 100.0,
    HealthStatus.DEGRADED: 75.0,
    HealthStatus.WARNING: 50.0,
    HealthStatus.UNHEALTHY: 25.0,
    HealthStatus.MAINTENANCE: 0.0,
    HealthStatus.UNKNOWN: 0.0,
}


def compute_overall_status(
    statuses: Iterable[HealthStatus], *, maintenance_mode: bool = False
) -> HealthStatus:
    """Roll up every individually collected health-check-type status for
    one target into its own single overall status.
    """
    return calculate_status(statuses, maintenance_mode=maintenance_mode)


def compute_blast_radius_status(
    own_status: HealthStatus, dependency_statuses: Iterable[HealthStatus]
) -> HealthStatus:
    """A target's own effective status once its dependencies' own
    statuses are folded in -- a target that is itself healthy but
    depends on an unhealthy parent is not fully healthy.
    """
    return calculate_status([own_status, *dependency_statuses])


def score_from_status(status: HealthStatus) -> float:
    """A numeric 0-100 health score for *status* ("Overall Health Score"),
    for :class:`~app.models.monitoring_history.MonitoringHistory`/
    statistics trending -- ``HealthStatus`` itself carries no numeric
    weight of its own.
    """
    return _STATUS_SCORES[status]


__all__ = ["compute_blast_radius_status", "compute_overall_status", "score_from_status"]
