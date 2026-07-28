"""Retention policy resolution ("Retention Policies") -- picks the most
specific applicable :class:`~app.models.monitoring_retention
.MonitoringRetention` row for a metric type, falling back to the
organization's own default (a ``None``-``metric_type`` row), falling
back further to a hardcoded 90-day platform default if the
organization has configured no policy of its own at all.
"""

from __future__ import annotations

from app.models.enums import MetricType
from app.models.monitoring_retention import MonitoringRetention

_PLATFORM_DEFAULT_RETENTION_DAYS = 90


def resolve_retention_days(policies: list[MonitoringRetention], metric_type: MetricType) -> int:
    """Return the retention window (in days) that applies to *metric_type*."""
    specific = next((p for p in policies if p.metric_type == metric_type and p.is_active), None)
    if specific is not None:
        return specific.retention_days
    default = next((p for p in policies if p.metric_type is None and p.is_active), None)
    if default is not None:
        return default.retention_days
    return _PLATFORM_DEFAULT_RETENTION_DAYS


__all__ = ["resolve_retention_days"]
