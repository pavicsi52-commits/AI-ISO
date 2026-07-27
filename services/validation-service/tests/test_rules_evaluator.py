"""Tests for :mod:`app.rules.evaluator` -- real Jinja2-sandboxed
condition evaluation via ``shared_core.workflow.expressions``, no
mocking of the evaluator itself.
"""

from __future__ import annotations

import uuid

from app.models.enums import ValidationResultStatus, ValidationSeverity
from app.models.validation_rule import ValidationRule
from app.rules.evaluator import evaluate_rule, evaluate_rule_chain


def _rule(
    condition: str,
    *,
    priority: int = 0,
    result_status: ValidationResultStatus = ValidationResultStatus.FAILED,
    severity: ValidationSeverity = ValidationSeverity.MEDIUM,
) -> ValidationRule:
    return ValidationRule(
        organization_id=uuid.uuid4(),
        check_id=uuid.uuid4(),
        name="test-rule",
        condition=condition,
        result_status=result_status,
        severity=severity,
        priority=priority,
    )


class TestEvaluateRule:
    def test_matching_condition_returns_rule_own_status(self) -> None:
        rule = _rule("disk_usage_percent > 90", result_status=ValidationResultStatus.FAILED)
        status = evaluate_rule(rule, {"disk_usage_percent": 95})
        assert status == ValidationResultStatus.FAILED

    def test_non_matching_condition_returns_passed(self) -> None:
        rule = _rule("disk_usage_percent > 90")
        status = evaluate_rule(rule, {"disk_usage_percent": 50})
        assert status == ValidationResultStatus.PASSED

    def test_broken_condition_returns_unknown(self) -> None:
        rule = _rule("missing_key > 90")
        status = evaluate_rule(rule, {"disk_usage_percent": 50})
        assert status == ValidationResultStatus.UNKNOWN

    def test_warning_severity_rule(self) -> None:
        rule = _rule(
            "disk_usage_percent > 80",
            result_status=ValidationResultStatus.WARNING,
            severity=ValidationSeverity.LOW,
        )
        status = evaluate_rule(rule, {"disk_usage_percent": 85})
        assert status == ValidationResultStatus.WARNING


class TestEvaluateRuleChain:
    def test_no_rules_returns_unknown(self) -> None:
        status, matched = evaluate_rule_chain([], {})
        assert status == ValidationResultStatus.UNKNOWN
        assert matched is None

    def test_all_rules_pass_returns_passed(self) -> None:
        rules = [_rule("disk_usage_percent > 95", priority=0)]
        status, matched = evaluate_rule_chain(rules, {"disk_usage_percent": 50})
        assert status == ValidationResultStatus.PASSED
        assert matched is None

    def test_first_matching_rule_wins_in_priority_order(self) -> None:
        warning_rule = _rule(
            "disk_usage_percent > 80", priority=0, result_status=ValidationResultStatus.WARNING
        )
        critical_rule = _rule(
            "disk_usage_percent > 95", priority=1, result_status=ValidationResultStatus.FAILED
        )
        status, matched = evaluate_rule_chain(
            [warning_rule, critical_rule], {"disk_usage_percent": 97}
        )
        assert status == ValidationResultStatus.WARNING
        assert matched is warning_rule

    def test_later_priority_rule_matches_when_earlier_does_not(self) -> None:
        warning_rule = _rule(
            "disk_usage_percent > 80", priority=0, result_status=ValidationResultStatus.WARNING
        )
        critical_rule = _rule(
            "disk_usage_percent > 95", priority=1, result_status=ValidationResultStatus.FAILED
        )
        status, matched = evaluate_rule_chain(
            [warning_rule, critical_rule], {"disk_usage_percent": 60}
        )
        assert status == ValidationResultStatus.PASSED
        assert matched is None
