"""Unit tests for :mod:`app.rules.evaluator`/:mod:`app.rules.thresholds`."""

from __future__ import annotations

import uuid

from shared_core.monitoring.thresholds import ThresholdLevel

from app.models.enums import MonitoringRuleType, ThresholdType
from app.models.monitoring_rule import MonitoringRule
from app.models.monitoring_threshold import MonitoringThreshold
from app.rules.evaluator import evaluate_rule
from app.rules.thresholds import evaluate_threshold, to_shared_threshold


def _rule(condition: str) -> MonitoringRule:
    return MonitoringRule(
        organization_id=uuid.uuid4(),
        metric_id=uuid.uuid4(),
        rule_type=MonitoringRuleType.METRIC,
        name="test-rule",
        condition=condition,
        severity=ThresholdLevel.HIGH,
    )


class TestEvaluateRule:
    def test_matching_condition_returns_true(self) -> None:
        assert evaluate_rule(_rule("value > 10"), {"value": 20}) is True

    def test_non_matching_condition_returns_false(self) -> None:
        assert evaluate_rule(_rule("value > 10"), {"value": 5}) is False

    def test_malformed_condition_returns_false(self) -> None:
        assert evaluate_rule(_rule("value >>> 10"), {"value": 5}) is False

    def test_missing_variable_returns_false(self) -> None:
        assert evaluate_rule(_rule("missing_var > 10"), {"value": 5}) is False


def _threshold(**kwargs: float | None) -> MonitoringThreshold:
    return MonitoringThreshold(
        organization_id=uuid.uuid4(),
        metric_id=uuid.uuid4(),
        threshold_type=ThresholdType.STATIC,
        **kwargs,
    )


class TestThresholds:
    def test_to_shared_threshold_maps_every_level(self) -> None:
        threshold = _threshold(informational=1.0, low=2.0, medium=3.0, high=4.0, critical=5.0)
        shared = to_shared_threshold(threshold, metric_name="cpu")
        assert shared.metric_name == "cpu"
        assert shared.informational == 1.0
        assert shared.low == 2.0
        assert shared.medium == 3.0
        assert shared.high == 4.0
        assert shared.critical == 5.0

    def test_evaluate_threshold_returns_highest_breached_level(self) -> None:
        threshold = _threshold(high=100.0, critical=200.0)
        assert evaluate_threshold(threshold, 250.0, metric_name="cpu") == ThresholdLevel.CRITICAL
        assert evaluate_threshold(threshold, 150.0, metric_name="cpu") == ThresholdLevel.HIGH

    def test_evaluate_threshold_returns_none_when_no_breach(self) -> None:
        threshold = _threshold(high=100.0, critical=200.0)
        assert evaluate_threshold(threshold, 50.0, metric_name="cpu") is None
