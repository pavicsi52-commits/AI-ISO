"""Converts a persisted
:class:`~app.models.monitoring_threshold.MonitoringThreshold` row into
``shared_core.monitoring.thresholds.Threshold`` at evaluation time,
reusing that dataclass's own ``evaluate()`` breach logic rather than
duplicating it here ("THRESHOLDS" "Support").
"""

from __future__ import annotations

from shared_core.monitoring.thresholds import Threshold, ThresholdLevel

from app.models.monitoring_threshold import MonitoringThreshold


def to_shared_threshold(threshold: MonitoringThreshold, *, metric_name: str) -> Threshold:
    """Return *threshold* as a ``shared_core`` :class:`Threshold`."""
    return Threshold(
        metric_name=metric_name,
        informational=threshold.informational,
        low=threshold.low,
        medium=threshold.medium,
        high=threshold.high,
        critical=threshold.critical,
    )


def evaluate_threshold(
    threshold: MonitoringThreshold, value: float, *, metric_name: str
) -> ThresholdLevel | None:
    """Return the highest-severity level *value* breaches on *threshold*, or
    ``None`` if it breaches none.
    """
    return to_shared_threshold(threshold, metric_name=metric_name).evaluate(value)


__all__ = ["evaluate_threshold", "to_shared_threshold"]
