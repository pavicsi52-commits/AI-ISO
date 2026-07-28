"""Composite scoring -- combines a target's own health score,
availability percentage, and SLA compliance into one overall figure for
statistics/reporting ("ANALYTICS" "Collect": Metric Trends,
Availability Trends). Distinct from
:func:`app.health.engine.score_from_status` (a per-status numeric
weight) -- this module blends several already-computed numbers together.
"""

from __future__ import annotations

_HEALTH_WEIGHT = 0.5
_AVAILABILITY_WEIGHT = 0.3
_SLA_WEIGHT = 0.2


def compute_composite_score(
    *, health_score: float, availability_percentage: float, sla_compliance_percentage: float
) -> float:
    """A single 0-100 composite score, weighting health 50%, availability
    30%, and SLA compliance 20%.
    """
    return (
        (health_score * _HEALTH_WEIGHT)
        + (availability_percentage * _AVAILABILITY_WEIGHT)
        + (sla_compliance_percentage * _SLA_WEIGHT)
    )


__all__ = ["compute_composite_score"]
