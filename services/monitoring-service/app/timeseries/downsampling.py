"""Downsamples raw
:class:`~app.models.monitoring_metric_series.MonitoringMetricSeries`
rows into fixed-width time buckets ("Downsampling", "Compression") --
reduces a high-frequency series down to one aggregated point per
configured interval, per a retention policy's own
``downsampling_function``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta

from app.models.enums import AggregationFunction
from app.models.monitoring_metric_series import MonitoringMetricSeries
from app.timeseries.aggregation import aggregate


def downsample(
    points: Sequence[MonitoringMetricSeries],
    *,
    interval_seconds: float,
    function: AggregationFunction,
) -> list[tuple[datetime, float]]:
    """Bucket *points* into fixed *interval_seconds* windows, aggregating
    each bucket with *function*. *points* need not be pre-sorted.
    """
    if not points:
        return []
    ordered = sorted(points, key=lambda point: point.recorded_at)
    epoch = ordered[0].recorded_at
    buckets: dict[int, list[float]] = defaultdict(list)
    for point in ordered:
        bucket_index = int((point.recorded_at - epoch).total_seconds() // interval_seconds)
        buckets[bucket_index].append(point.value)
    return [
        (epoch + timedelta(seconds=bucket_index * interval_seconds), aggregate(values, function))
        for bucket_index, values in sorted(buckets.items())
    ]


__all__ = ["downsample"]
