"""Response schema for ``GET /monitoring/performance``.

Docs/044's own 17-table list has no dedicated ``monitoring_performance``
table -- "Performance Monitoring" (Response Time, Throughput, Resource
Utilization, Queue Length, Error Rates, Capacity Planning) is a
*computed view* over the same
:class:`~app.models.monitoring_metric_series.MonitoringMetricSeries`
rows every other collector already writes into, filtered to the subset
of :class:`~app.models.enums.MetricType` values that are
performance-relevant (``LATENCY``, ``IOPS``, ``BANDWIDTH``,
``PACKET_LOSS``), rather than a duplicated persistence path.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.models.enums import MetricType


class MonitoringPerformanceMetricSummary(BaseModel):
    """One performance-relevant metric's own summary statistics over a window."""

    metric_type: MetricType
    average: float
    minimum: float
    maximum: float
    p95: float
    sample_count: int


class MonitoringPerformanceResponse(BaseModel):
    """A target's own performance summary over a window."""

    target_id: UUID
    metrics: list[MonitoringPerformanceMetricSummary]


__all__ = ["MonitoringPerformanceMetricSummary", "MonitoringPerformanceResponse"]
