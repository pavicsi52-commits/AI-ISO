"""Unit tests for :mod:`app.timeseries.aggregation`/``downsampling``/``retention``."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.enums import AggregationFunction, MetricType
from app.models.monitoring_metric_series import MonitoringMetricSeries
from app.models.monitoring_retention import MonitoringRetention
from app.timeseries.aggregation import aggregate
from app.timeseries.downsampling import downsample
from app.timeseries.retention import resolve_retention_days


class TestAggregate:
    def test_avg(self) -> None:
        assert aggregate([1.0, 2.0, 3.0], AggregationFunction.AVG) == 2.0

    def test_sum(self) -> None:
        assert aggregate([1.0, 2.0, 3.0], AggregationFunction.SUM) == 6.0

    def test_min(self) -> None:
        assert aggregate([3.0, 1.0, 2.0], AggregationFunction.MIN) == 1.0

    def test_max(self) -> None:
        assert aggregate([3.0, 1.0, 2.0], AggregationFunction.MAX) == 3.0

    def test_count(self) -> None:
        assert aggregate([1.0, 2.0, 3.0], AggregationFunction.COUNT) == 3.0

    def test_p95_single_value(self) -> None:
        assert aggregate([42.0], AggregationFunction.P95) == 42.0

    def test_p95_interpolates(self) -> None:
        values = [float(v) for v in range(1, 101)]
        result = aggregate(values, AggregationFunction.P95)
        assert 94.0 <= result <= 96.0

    def test_p99(self) -> None:
        values = [float(v) for v in range(1, 101)]
        result = aggregate(values, AggregationFunction.P99)
        assert 98.0 <= result <= 100.0

    def test_empty_values_returns_zero(self) -> None:
        assert aggregate([], AggregationFunction.AVG) == 0.0


def _point(value: float, recorded_at: datetime) -> MonitoringMetricSeries:
    return MonitoringMetricSeries(
        organization_id=uuid.uuid4(),
        metric_id=uuid.uuid4(),
        target_id=uuid.uuid4(),
        value=value,
        recorded_at=recorded_at,
    )


class TestDownsample:
    def test_empty_points_returns_empty(self) -> None:
        assert downsample([], interval_seconds=60.0, function=AggregationFunction.AVG) == []

    def test_buckets_points_into_fixed_windows(self) -> None:
        base = datetime(2026, 1, 1, tzinfo=UTC)
        points = [
            _point(10.0, base),
            _point(20.0, base + timedelta(seconds=10)),
            _point(100.0, base + timedelta(seconds=70)),
        ]
        result = downsample(points, interval_seconds=60.0, function=AggregationFunction.AVG)
        assert len(result) == 2
        assert result[0][1] == 15.0
        assert result[1][1] == 100.0

    def test_out_of_order_points_are_sorted_first(self) -> None:
        base = datetime(2026, 1, 1, tzinfo=UTC)
        points = [_point(100.0, base + timedelta(seconds=70)), _point(10.0, base)]
        result = downsample(points, interval_seconds=60.0, function=AggregationFunction.AVG)
        assert result[0][1] == 10.0
        assert result[1][1] == 100.0


class TestResolveRetentionDays:
    def test_specific_policy_wins(self) -> None:
        policies = [
            MonitoringRetention(
                organization_id=uuid.uuid4(), metric_type=None, retention_days=90, is_active=True
            ),
            MonitoringRetention(
                organization_id=uuid.uuid4(),
                metric_type=MetricType.CPU_USAGE,
                retention_days=30,
                is_active=True,
            ),
        ]
        assert resolve_retention_days(policies, MetricType.CPU_USAGE) == 30

    def test_falls_back_to_org_default(self) -> None:
        policies = [
            MonitoringRetention(
                organization_id=uuid.uuid4(), metric_type=None, retention_days=45, is_active=True
            )
        ]
        assert resolve_retention_days(policies, MetricType.MEMORY_USAGE) == 45

    def test_falls_back_to_platform_default(self) -> None:
        assert resolve_retention_days([], MetricType.MEMORY_USAGE) == 90

    @pytest.mark.parametrize("is_active", [False])
    def test_inactive_policy_is_ignored(self, is_active: bool) -> None:
        policies = [
            MonitoringRetention(
                organization_id=uuid.uuid4(),
                metric_type=MetricType.CPU_USAGE,
                retention_days=30,
                is_active=is_active,
            )
        ]
        assert resolve_retention_days(policies, MetricType.CPU_USAGE) == 90
