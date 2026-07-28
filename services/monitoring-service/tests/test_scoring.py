"""Unit tests for :mod:`app.scoring.composite`."""

from __future__ import annotations

from app.scoring.composite import compute_composite_score


class TestComputeCompositeScore:
    def test_perfect_scores_yield_100(self) -> None:
        score = compute_composite_score(
            health_score=100.0, availability_percentage=100.0, sla_compliance_percentage=100.0
        )
        assert score == 100.0

    def test_zero_scores_yield_zero(self) -> None:
        score = compute_composite_score(
            health_score=0.0, availability_percentage=0.0, sla_compliance_percentage=0.0
        )
        assert score == 0.0

    def test_weights_health_most_heavily(self) -> None:
        health_only = compute_composite_score(
            health_score=100.0, availability_percentage=0.0, sla_compliance_percentage=0.0
        )
        availability_only = compute_composite_score(
            health_score=0.0, availability_percentage=100.0, sla_compliance_percentage=0.0
        )
        assert health_only > availability_only
