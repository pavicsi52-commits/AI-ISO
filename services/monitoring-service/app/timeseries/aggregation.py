"""Time-series aggregation -- "TIME SERIES" "Support": Aggregation,
Historical Queries, Time-window Analysis. Pure, in-memory statistics
over a list of already-fetched
:class:`~app.models.monitoring_metric_series.MonitoringMetricSeries`
values -- the potentially large scan itself is the repository's own
job (``list_for_target``), this module only reduces the results.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from app.models.enums import AggregationFunction

_REDUCERS: dict[AggregationFunction, Callable[[Sequence[float]], float]] = {
    AggregationFunction.AVG: lambda values: sum(values) / len(values),
    AggregationFunction.SUM: sum,
    AggregationFunction.MIN: min,
    AggregationFunction.MAX: max,
    AggregationFunction.COUNT: lambda values: float(len(values)),
    AggregationFunction.P95: lambda values: _percentile(values, 0.95),
    AggregationFunction.P99: lambda values: _percentile(values, 0.99),
}


def aggregate(values: Sequence[float], function: AggregationFunction) -> float:
    """Reduce *values* to a single number using *function*.

    Raises:
        ValueError: If *function* is not a recognized :class:`AggregationFunction`.
    """
    if not values:
        return 0.0
    reducer = _REDUCERS.get(function)
    if reducer is None:
        raise ValueError(f"Unsupported aggregation function {function!r}.")
    return reducer(values)


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = fraction * (len(ordered) - 1)
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    weight = index - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


__all__ = ["aggregate"]
