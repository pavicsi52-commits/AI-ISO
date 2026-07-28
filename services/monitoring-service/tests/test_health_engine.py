"""Unit tests for :mod:`app.health.engine`."""

from __future__ import annotations

from shared_core.enums.health_status import HealthStatus

from app.health.engine import compute_blast_radius_status, compute_overall_status, score_from_status


class TestComputeOverallStatus:
    def test_worst_status_wins(self) -> None:
        result = compute_overall_status([HealthStatus.HEALTHY, HealthStatus.UNHEALTHY])
        assert result == HealthStatus.UNHEALTHY

    def test_empty_statuses_returns_unknown(self) -> None:
        assert compute_overall_status([]) == HealthStatus.UNKNOWN

    def test_maintenance_mode_overrides_everything(self) -> None:
        result = compute_overall_status([HealthStatus.HEALTHY], maintenance_mode=True)
        assert result == HealthStatus.MAINTENANCE


class TestComputeBlastRadiusStatus:
    def test_healthy_target_with_unhealthy_dependency_degrades(self) -> None:
        result = compute_blast_radius_status(HealthStatus.HEALTHY, [HealthStatus.UNHEALTHY])
        assert result == HealthStatus.UNHEALTHY

    def test_no_dependencies_keeps_own_status(self) -> None:
        result = compute_blast_radius_status(HealthStatus.HEALTHY, [])
        assert result == HealthStatus.HEALTHY


class TestScoreFromStatus:
    def test_healthy_scores_100(self) -> None:
        assert score_from_status(HealthStatus.HEALTHY) == 100.0

    def test_unhealthy_scores_25(self) -> None:
        assert score_from_status(HealthStatus.UNHEALTHY) == 25.0

    def test_every_status_has_a_score(self) -> None:
        for status in HealthStatus:
            assert 0.0 <= score_from_status(status) <= 100.0
