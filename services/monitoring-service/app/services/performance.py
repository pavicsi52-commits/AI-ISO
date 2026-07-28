"""Computes a target's own performance summary over a window
("PERFORMANCE" "Monitor": Response Time, Throughput, Resource
Utilization) -- a view over
:class:`~app.models.monitoring_metric_series.MonitoringMetricSeries`
filtered to performance-relevant metric types, shared by
``GET /monitoring/performance`` and the ``PERFORMANCE`` report type
(see :mod:`app.schemas.performance`'s own docstring for why this is a
computed view rather than its own table).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any
from uuid import UUID

from app.models.enums import AggregationFunction, MetricType
from app.repositories.monitoring_metric import MonitoringMetricRepository
from app.repositories.monitoring_metric_series import MonitoringMetricSeriesRepository
from app.timeseries.aggregation import aggregate

_PERFORMANCE_METRIC_TYPES = frozenset(
    {MetricType.LATENCY, MetricType.IOPS, MetricType.BANDWIDTH, MetricType.PACKET_LOSS}
)


class MonitoringPerformanceService:
    """Computes performance-relevant metric summaries for a target."""

    def __init__(
        self, series: MonitoringMetricSeriesRepository, metrics: MonitoringMetricRepository
    ) -> None:
        self._series = series
        self._metrics = metrics

    async def summarize_for_target(
        self, target_id: UUID, *, since: datetime | None = None
    ) -> list[dict[str, Any]]:
        """Every performance-relevant metric's own summary statistics for
        *target_id* over the given window.
        """
        points = await self._series.list_for_target(target_id, since=since)
        values_by_metric: dict[UUID, list[float]] = defaultdict(list)
        for point in points:
            values_by_metric[point.metric_id].append(point.value)

        summaries: list[dict[str, Any]] = []
        for metric_id, values in values_by_metric.items():
            metric = await self._metrics.get_by_id(metric_id)
            if metric is None or metric.metric_type not in _PERFORMANCE_METRIC_TYPES:
                continue
            summaries.append(
                {
                    "metric_type": metric.metric_type,
                    "average": aggregate(values, AggregationFunction.AVG),
                    "minimum": aggregate(values, AggregationFunction.MIN),
                    "maximum": aggregate(values, AggregationFunction.MAX),
                    "p95": aggregate(values, AggregationFunction.P95),
                    "sample_count": len(values),
                }
            )
        return summaries


__all__ = ["MonitoringPerformanceService"]
