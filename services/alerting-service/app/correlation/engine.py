"""Alert correlation ("CORRELATION" "Support").

Given a newly raised alert and the alerts already open in its own time
window, decides which existing alert (if any) it should be correlated
*to* as a child -- i.e. which one looks like the root cause. Pure
decision logic over already-fetched rows; persistence belongs to the
calling service.

**Honest scope note**: ``TOPOLOGY``/``DEPENDENCY`` correlation here
matches on *shared identity references* (two alerts naming the same
``target_id``, or one naming another's own referenced resource), not on
a live topology graph walk. This service holds no topology of its own,
and ``services/monitoring-service``'s own dependency graph
(``monitoring_dependencies``) is exposed over REST but reachable only
with a caller token -- which a scheduler-fired correlation pass does
not have (the same platform-wide "no service-account credential
mechanism exists yet" gap every prior AI-IOS service has documented).
Shared-reference correlation is real and useful on its own; a genuine
graph-walking correlation is deferred rather than faked with a stubbed
graph.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from shared_core.enums.severity import Severity

from app.models.alert_instance import AlertInstance
from app.models.enums import CorrelationType

_SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}
"""Lower rank = more severe. Used to pick the most severe candidate as
the presumed root cause when several correlate equally well.
"""


@dataclass(frozen=True, slots=True)
class CorrelationDecision:
    """The alert a new alert should be correlated to, and why."""

    parent: AlertInstance
    correlation_type: CorrelationType


def _shared_reference(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if not left or not right:
        return False
    left_values = {str(value) for value in left.values() if value is not None}
    right_values = {str(value) for value in right.values() if value is not None}
    return bool(left_values & right_values)


def _rank(alert: AlertInstance) -> tuple[int, float]:
    severity = alert.severity if isinstance(alert.severity, Severity) else Severity(alert.severity)
    return (_SEVERITY_RANK[severity], -alert.triggered_at.timestamp())


def correlate(
    alert: AlertInstance,
    candidates: Sequence[AlertInstance],
    *,
    window: timedelta,
) -> CorrelationDecision | None:
    """Return the alert *alert* should be correlated to, or ``None``.

    Prefers a shared-reference match (``DEPENDENCY``) over a purely
    temporal one (``TIME``): two alerts naming the same resource are
    far more likely genuinely related than two that merely happened
    close together. Among equally-matching candidates the most severe
    (then most recent) wins, since that is the better root-cause
    candidate. An alert never correlates to itself, nor to one that
    fired *after* it.
    """
    same_reference: list[AlertInstance] = []
    same_window: list[AlertInstance] = []

    for candidate in candidates:
        if candidate.id == alert.id:
            continue
        if candidate.triggered_at > alert.triggered_at:
            continue
        if alert.triggered_at - candidate.triggered_at > window:
            continue
        if _shared_reference(alert.source_reference, candidate.source_reference):
            same_reference.append(candidate)
        else:
            same_window.append(candidate)

    if same_reference:
        return CorrelationDecision(
            parent=min(same_reference, key=_rank), correlation_type=CorrelationType.DEPENDENCY
        )
    if same_window:
        return CorrelationDecision(
            parent=min(same_window, key=_rank), correlation_type=CorrelationType.TIME
        )
    return None


__all__ = ["CorrelationDecision", "correlate"]
