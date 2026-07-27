"""Tests for :mod:`app.scoring.engine` -- the weighted scoring aggregator."""

from __future__ import annotations

import uuid

from app.models.enums import ValidationResultStatus, ValidationType
from app.models.validation_result import ValidationResult
from app.models.validation_rule import ValidationRule
from app.scoring.engine import compute_scores


def _result(
    status: ValidationResultStatus,
    *,
    check_id: uuid.UUID | None = None,
    rule_id: uuid.UUID | None = None,
) -> ValidationResult:
    return ValidationResult(
        organization_id=uuid.uuid4(),
        execution_id=uuid.uuid4(),
        target_id=uuid.uuid4(),
        check_id=check_id or uuid.uuid4(),
        check_type="connectivity",
        rule_id=rule_id,
        status=status,
    )


def _rule(weight: float) -> ValidationRule:
    return ValidationRule(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        check_id=uuid.uuid4(),
        name="rule",
        condition="true",
        weight=weight,
    )


class TestComputeScores:
    def test_all_passed_yields_full_score(self) -> None:
        results = [_result(ValidationResultStatus.PASSED) for _ in range(3)]
        scores = compute_scores(results, {}, {})
        assert scores["overall_score"] == 100.0

    def test_all_failed_yields_zero_score(self) -> None:
        results = [_result(ValidationResultStatus.FAILED) for _ in range(3)]
        scores = compute_scores(results, {}, {})
        assert scores["overall_score"] == 0.0

    def test_warning_counts_as_half_credit(self) -> None:
        results = [_result(ValidationResultStatus.WARNING)]
        scores = compute_scores(results, {}, {})
        assert scores["overall_score"] == 50.0

    def test_skipped_and_not_applicable_excluded_entirely(self) -> None:
        results = [
            _result(ValidationResultStatus.PASSED),
            _result(ValidationResultStatus.SKIPPED),
            _result(ValidationResultStatus.NOT_APPLICABLE),
        ]
        scores = compute_scores(results, {}, {})
        assert scores["overall_score"] == 100.0

    def test_no_results_yields_zero_overall_score(self) -> None:
        scores = compute_scores([], {}, {})
        assert scores["overall_score"] == 0.0

    def test_category_with_no_results_is_none(self) -> None:
        results = [_result(ValidationResultStatus.PASSED)]
        scores = compute_scores(results, {}, {})
        assert scores["security_score"] is None

    def test_rule_weight_affects_overall_score(self) -> None:
        heavy_rule = _rule(weight=3.0)
        light_rule = _rule(weight=1.0)
        results = [
            _result(ValidationResultStatus.FAILED, rule_id=heavy_rule.id),
            _result(ValidationResultStatus.PASSED, rule_id=light_rule.id),
        ]
        rules_by_id = {str(heavy_rule.id): heavy_rule, str(light_rule.id): light_rule}
        scores = compute_scores(results, rules_by_id, {})
        # (0 * 3 + 1 * 1) / (3 + 1) * 100 = 25.0
        assert scores["overall_score"] == 25.0

    def test_category_score_computed_from_validation_type_mapping(self) -> None:
        check_id = uuid.uuid4()
        results = [_result(ValidationResultStatus.PASSED, check_id=check_id)]
        scores = compute_scores(results, {}, {str(check_id): ValidationType.SECURITY})
        assert scores["security_score"] == 100.0
        assert scores["compliance_score"] is None

    def test_custom_validation_type_contributes_to_overall_only(self) -> None:
        check_id = uuid.uuid4()
        results = [_result(ValidationResultStatus.FAILED, check_id=check_id)]
        scores = compute_scores(results, {}, {str(check_id): ValidationType.CUSTOM})
        assert scores["overall_score"] == 0.0
        assert all(
            scores[key] is None
            for key in (
                "infrastructure_score",
                "security_score",
                "compliance_score",
                "configuration_score",
                "performance_score",
                "health_score",
            )
        )
