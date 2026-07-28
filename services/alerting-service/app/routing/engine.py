"""Alert routing ("ROUTING" "Support").

Selects which configured :class:`~app.models.alert_route.AlertRoute`
rows an alert should be delivered through. Pure selection logic over
already-fetched rows; actually delivering is
:class:`app.notifications.alert_notifications.AlertNotificationService`'s
job.

A route with ``severity_filter IS NULL`` matches every severity; one
with a value matches that severity **and anything more severe**, which
is what an operator configuring "page me for HIGH" invariably means --
a CRITICAL alert must never slip past a HIGH-filtered route.
"""

from __future__ import annotations

from collections.abc import Sequence

from shared_core.enums.severity import Severity

from app.models.alert_route import AlertRoute

_SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}
"""Lower rank = more severe."""


def _as_severity(value: Severity | str) -> Severity:
    return value if isinstance(value, Severity) else Severity(value)


def route_matches(route: AlertRoute, severity: Severity | str) -> bool:
    """Return whether *route* should fire for an alert of *severity*."""
    if not route.enabled:
        return False
    if route.severity_filter is None:
        return True
    return (
        _SEVERITY_RANK[_as_severity(severity)]
        <= _SEVERITY_RANK[_as_severity(route.severity_filter)]
    )


def select_routes(routes: Sequence[AlertRoute], severity: Severity | str) -> list[AlertRoute]:
    """Every route that should deliver an alert of *severity*."""
    return [route for route in routes if route_matches(route, severity)]


__all__ = ["route_matches", "select_routes"]
