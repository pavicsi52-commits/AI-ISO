"""Risk scoring: the likelihood/impact matrix, six dimensions, banding.

Pure -- no fixtures, no database.
"""

from __future__ import annotations

import pytest

from app.models.enums import ChangeType, RiskImpact, RiskLevel, RiskLikelihood
from app.risk.engine import (
    RiskDimensions,
    approval_recommendation_for,
    automated_score,
    dimension_score,
    effective_risk_level,
    matrix_score,
    risk_level_for,
)


def _dimensions(level: RiskImpact = RiskImpact.MINIMAL) -> RiskDimensions:
    return RiskDimensions(
        technical=level,
        business=level,
        operational=level,
        security=level,
        compliance=level,
        dependency=level,
    )


class TestMatrixScore:
    def test_lowest_likelihood_and_impact_score_zero(self) -> None:
        assert matrix_score(RiskLikelihood.RARE, RiskImpact.MINIMAL) == 0.0

    def test_highest_likelihood_and_impact_score_one(self) -> None:
        assert matrix_score(RiskLikelihood.ALMOST_CERTAIN, RiskImpact.SEVERE) == 1.0

    def test_score_increases_with_either_axis(self) -> None:
        low = matrix_score(RiskLikelihood.RARE, RiskImpact.MODERATE)
        high = matrix_score(RiskLikelihood.LIKELY, RiskImpact.MODERATE)
        assert high > low


class TestDimensionScore:
    def test_all_minimal_scores_zero(self) -> None:
        assert dimension_score(_dimensions(RiskImpact.MINIMAL)) == 0.0

    def test_all_severe_scores_one(self) -> None:
        assert dimension_score(_dimensions(RiskImpact.SEVERE)) == 1.0

    def test_one_severe_dimension_dominates_the_rest(self) -> None:
        dimensions = RiskDimensions(
            technical=RiskImpact.MINIMAL,
            business=RiskImpact.MINIMAL,
            operational=RiskImpact.MINIMAL,
            security=RiskImpact.SEVERE,
            compliance=RiskImpact.MINIMAL,
            dependency=RiskImpact.MINIMAL,
        )
        assert dimension_score(dimensions) == 1.0


class TestAutomatedScore:
    def test_takes_the_worse_of_matrix_and_dimensions(self) -> None:
        # A high matrix score with minimal dimensions should not be
        # diluted by the dimensions, and vice versa.
        high_matrix = automated_score(
            likelihood=RiskLikelihood.ALMOST_CERTAIN,
            impact=RiskImpact.SEVERE,
            dimensions=_dimensions(RiskImpact.MINIMAL),
        )
        assert high_matrix == 1.0

        high_dimension = automated_score(
            likelihood=RiskLikelihood.RARE,
            impact=RiskImpact.MINIMAL,
            dimensions=_dimensions(RiskImpact.SEVERE),
        )
        assert high_dimension == 1.0


class TestRiskLevelFor:
    def test_zero_is_low(self) -> None:
        assert risk_level_for(0.0) is RiskLevel.LOW

    def test_just_below_medium_threshold_is_low(self) -> None:
        assert risk_level_for(0.24) is RiskLevel.LOW

    def test_medium_threshold_is_medium(self) -> None:
        assert risk_level_for(0.25) is RiskLevel.MEDIUM

    def test_high_threshold_is_high(self) -> None:
        assert risk_level_for(0.50) is RiskLevel.HIGH

    def test_critical_threshold_is_critical(self) -> None:
        assert risk_level_for(0.75) is RiskLevel.CRITICAL

    def test_one_is_critical(self) -> None:
        assert risk_level_for(1.0) is RiskLevel.CRITICAL


class TestEffectiveRiskLevel:
    def test_no_override_returns_the_automated_level(self) -> None:
        assert effective_risk_level(automated=RiskLevel.LOW, override=None) is RiskLevel.LOW

    def test_an_override_replaces_the_automated_level(self) -> None:
        assert (
            effective_risk_level(automated=RiskLevel.LOW, override=RiskLevel.CRITICAL)
            is RiskLevel.CRITICAL
        )


class TestApprovalRecommendationFor:
    def test_standard_change_needs_no_extra_approval(self) -> None:
        recommendation = approval_recommendation_for(RiskLevel.LOW, ChangeType.STANDARD)
        assert "pre-approved" in recommendation.lower()

    def test_emergency_change_recommends_implementing_now(self) -> None:
        recommendation = approval_recommendation_for(RiskLevel.CRITICAL, ChangeType.EMERGENCY)
        assert "implement now" in recommendation.lower()

    def test_critical_risk_normal_change_recommends_full_cab(self) -> None:
        recommendation = approval_recommendation_for(RiskLevel.CRITICAL, ChangeType.NORMAL)
        assert "cab" in recommendation.lower()

    def test_low_risk_normal_change_recommends_expedited_approval(self) -> None:
        recommendation = approval_recommendation_for(RiskLevel.LOW, ChangeType.NORMAL)
        assert "expedited" in recommendation.lower()

    @pytest.mark.parametrize("risk_level", list(RiskLevel))
    def test_every_risk_level_produces_a_non_empty_recommendation(
        self, risk_level: RiskLevel
    ) -> None:
        assert approval_recommendation_for(risk_level, ChangeType.NORMAL)
