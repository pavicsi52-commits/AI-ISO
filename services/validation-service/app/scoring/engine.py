"""The weighted scoring engine ("SCORING" "Generate": Overall Score,
Infrastructure Score, Security Score, Compliance Score, Configuration
Score, Performance Score, Health Score, Weighted Scoring). No
``shared_core`` equivalent exists (confirmed: no weighted-scoring
aggregator lives anywhere in ``packages/shared-core``), so this is
built directly on top of a completed execution's own
:class:`~app.models.validation_result.ValidationResult` rows.

Each result contributes ``credit * weight`` to its own category's
running total, where ``credit`` is 1.0 for
:attr:`~app.models.enums.ValidationResultStatus.PASSED`, 0.5 for
:attr:`~app.models.enums.ValidationResultStatus.WARNING` (a partial
pass), and 0.0 for every other terminal outcome;
``SKIPPED``/``NOT_APPLICABLE`` results are excluded entirely from both
numerator and denominator rather than counting as either a pass or a
fail. A category score is ``None`` when no result in the execution
falls into that category at all.

**A category-mapping design decision**: docs/043 names 20
:class:`~app.models.enums.ValidationType` values but only 6 named score
categories -- ``_TYPE_TO_CATEGORY`` below is this engine's own explicit,
documented mapping from the former onto the latter (``CUSTOM`` maps to
neither, contributing only to ``overall_score``).
"""

from __future__ import annotations

from collections import defaultdict

from app.models.enums import ValidationResultStatus, ValidationType
from app.models.validation_result import ValidationResult
from app.models.validation_rule import ValidationRule

_CREDIT: dict[ValidationResultStatus, float] = {
    ValidationResultStatus.PASSED: 1.0,
    ValidationResultStatus.WARNING: 0.5,
    ValidationResultStatus.FAILED: 0.0,
    ValidationResultStatus.TIMEOUT: 0.0,
    ValidationResultStatus.CANCELLED: 0.0,
    ValidationResultStatus.UNKNOWN: 0.0,
}
_EXCLUDED = frozenset({ValidationResultStatus.SKIPPED, ValidationResultStatus.NOT_APPLICABLE})

_TYPE_TO_CATEGORY: dict[ValidationType, str] = {
    ValidationType.INFRASTRUCTURE: "infrastructure_score",
    ValidationType.ENVIRONMENT: "infrastructure_score",
    ValidationType.NETWORK: "infrastructure_score",
    ValidationType.STORAGE: "infrastructure_score",
    ValidationType.CLOUD: "infrastructure_score",
    ValidationType.KUBERNETES: "infrastructure_score",
    ValidationType.INDUSTRIAL: "infrastructure_score",
    ValidationType.FIRMWARE: "infrastructure_score",
    ValidationType.PATCH: "infrastructure_score",
    ValidationType.SECURITY: "security_score",
    ValidationType.COMPLIANCE: "compliance_score",
    ValidationType.CONFIGURATION: "configuration_score",
    ValidationType.DEPLOYMENT: "configuration_score",
    ValidationType.POST_DEPLOYMENT: "configuration_score",
    ValidationType.PERFORMANCE: "performance_score",
    ValidationType.HEALTH: "health_score",
    ValidationType.CONNECTIVITY: "health_score",
    ValidationType.BACKUP: "health_score",
    ValidationType.DISASTER_RECOVERY: "health_score",
}

_SCORE_CATEGORIES = (
    "infrastructure_score",
    "security_score",
    "compliance_score",
    "configuration_score",
    "performance_score",
    "health_score",
)


def compute_scores(
    results: list[ValidationResult],
    rules_by_id: dict[str, ValidationRule],
    validation_types_by_check: dict[str, ValidationType],
) -> dict[str, float | None]:
    """Compute the overall and per-category weighted scores for one execution's results.

    *rules_by_id* maps each result's own ``rule_id`` (as a string) to
    its :class:`ValidationRule`, for the ``weight`` it contributes.
    *validation_types_by_check* maps each result's own ``check_id`` (as
    a string) to the :class:`~app.models.enums.ValidationType` its own
    category belongs to, for category attribution. A result with no
    matching entry in either mapping falls back to weight ``1.0`` and
    no category (counting only toward ``overall_score``).

    Returns a dict with keys ``overall_score`` plus one per entry in
    ``_SCORE_CATEGORIES``, each either a ``0``-``100`` float or
    ``None`` if no result touched that category.
    """
    overall_numerator = 0.0
    overall_denominator = 0.0
    category_numerator: dict[str, float] = defaultdict(float)
    category_denominator: dict[str, float] = defaultdict(float)

    for result in results:
        if result.status in _EXCLUDED:
            continue
        credit = _CREDIT.get(result.status, 0.0)
        rule = rules_by_id.get(str(result.rule_id)) if result.rule_id is not None else None
        weight = rule.weight if rule is not None else 1.0

        overall_numerator += credit * weight
        overall_denominator += weight

        validation_type = validation_types_by_check.get(str(result.check_id))
        category = _TYPE_TO_CATEGORY.get(validation_type) if validation_type is not None else None
        if category is not None:
            category_numerator[category] += credit * weight
            category_denominator[category] += weight

    scores: dict[str, float | None] = {
        "overall_score": (
            (overall_numerator / overall_denominator) * 100 if overall_denominator else 0.0
        )
    }
    for category in _SCORE_CATEGORIES:
        denominator = category_denominator.get(category, 0.0)
        scores[category] = (
            (category_numerator[category] / denominator) * 100 if denominator else None
        )
    return scores


__all__ = ["compute_scores"]
