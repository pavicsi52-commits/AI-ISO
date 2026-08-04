"""Evaluating a multi-level approval chain.

Pure -- no fixtures, no database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.approvals.engine import (
    ApprovalStep,
    active_level,
    chain_status,
    is_expired,
    level_status,
    levels_of,
    required_levels_for,
    steps_at_level,
)
from app.models.enums import ApprovalPolicy, ApprovalStatus, RiskLevel


def _step(level: int, status: ApprovalStatus, approver: str = "alice") -> ApprovalStep:
    return ApprovalStep(level=level, approver_id=approver, status=status)


class TestLevelsOf:
    def test_returns_distinct_levels_ascending(self) -> None:
        steps = [_step(2, ApprovalStatus.PENDING), _step(1, ApprovalStatus.PENDING)]
        assert levels_of(steps) == [1, 2]

    def test_empty_for_no_steps(self) -> None:
        assert levels_of([]) == []


class TestLevelStatus:
    def test_no_steps_is_pending(self) -> None:
        assert level_status([]) is ApprovalStatus.PENDING

    def test_all_approved_is_approved(self) -> None:
        steps = [_step(1, ApprovalStatus.APPROVED), _step(1, ApprovalStatus.APPROVED, "bob")]
        assert level_status(steps) is ApprovalStatus.APPROVED

    def test_a_single_rejection_fails_the_whole_level(self) -> None:
        steps = [_step(1, ApprovalStatus.APPROVED), _step(1, ApprovalStatus.REJECTED, "bob")]
        assert level_status(steps) is ApprovalStatus.REJECTED

    def test_a_conditional_approval_makes_the_level_conditional(self) -> None:
        steps = [_step(1, ApprovalStatus.APPROVED), _step(1, ApprovalStatus.CONDITIONAL, "bob")]
        assert level_status(steps) is ApprovalStatus.CONDITIONAL

    def test_one_pending_step_keeps_the_level_pending(self) -> None:
        steps = [_step(1, ApprovalStatus.APPROVED), _step(1, ApprovalStatus.PENDING, "bob")]
        assert level_status(steps) is ApprovalStatus.PENDING


class TestActiveLevel:
    def test_first_pending_level_is_active(self) -> None:
        steps = [_step(1, ApprovalStatus.APPROVED), _step(2, ApprovalStatus.PENDING)]
        assert active_level(steps) == 2

    def test_none_when_every_level_has_resolved(self) -> None:
        steps = [_step(1, ApprovalStatus.APPROVED), _step(2, ApprovalStatus.APPROVED)]
        assert active_level(steps) is None

    def test_level_one_is_active_even_if_level_two_has_steps(self) -> None:
        # A correctly-driven chain never has level-2 steps before level 1
        # resolves, but the engine must not be fooled if it happens.
        steps = [_step(1, ApprovalStatus.PENDING), _step(2, ApprovalStatus.APPROVED)]
        assert active_level(steps) == 1


class TestChainStatus:
    def test_no_steps_is_pending(self) -> None:
        assert chain_status([]) is ApprovalStatus.PENDING

    def test_single_level_all_approved_is_approved(self) -> None:
        steps = [_step(1, ApprovalStatus.APPROVED)]
        assert chain_status(steps) is ApprovalStatus.APPROVED

    def test_a_rejection_at_any_level_fails_the_whole_chain(self) -> None:
        steps = [_step(1, ApprovalStatus.APPROVED), _step(2, ApprovalStatus.REJECTED)]
        assert chain_status(steps) is ApprovalStatus.REJECTED

    def test_a_pending_level_below_the_top_keeps_the_chain_pending(self) -> None:
        steps = [_step(1, ApprovalStatus.PENDING), _step(2, ApprovalStatus.APPROVED)]
        assert chain_status(steps) is ApprovalStatus.PENDING

    def test_a_conditional_anywhere_makes_the_whole_chain_conditional(self) -> None:
        steps = [_step(1, ApprovalStatus.CONDITIONAL), _step(2, ApprovalStatus.APPROVED)]
        assert chain_status(steps) is ApprovalStatus.CONDITIONAL

    def test_two_full_levels_approved_is_approved(self) -> None:
        steps = [
            _step(1, ApprovalStatus.APPROVED),
            _step(1, ApprovalStatus.APPROVED, "bob"),
            _step(2, ApprovalStatus.APPROVED, "carol"),
        ]
        assert chain_status(steps) is ApprovalStatus.APPROVED


class TestIsExpired:
    def test_no_expiry_never_expires(self) -> None:
        assert is_expired(None, now=datetime.now(UTC)) is False

    def test_before_expiry_is_not_expired(self) -> None:
        future = datetime.now(UTC) + timedelta(hours=1)
        assert is_expired(future, now=datetime.now(UTC)) is False

    def test_at_or_after_expiry_is_expired(self) -> None:
        past = datetime.now(UTC) - timedelta(hours=1)
        assert is_expired(past, now=datetime.now(UTC)) is True


class TestRequiredLevelsFor:
    def test_single_policy_is_always_one_level(self) -> None:
        assert (
            required_levels_for(
                policy=ApprovalPolicy.SINGLE,
                risk_level=RiskLevel.CRITICAL,
                minimum_approvals_high_risk=5,
            )
            == 1
        )

    def test_risk_based_uses_the_configured_floor_for_high_risk(self) -> None:
        assert (
            required_levels_for(
                policy=ApprovalPolicy.RISK_BASED,
                risk_level=RiskLevel.HIGH,
                minimum_approvals_high_risk=3,
            )
            == 3
        )

    def test_risk_based_is_one_level_for_low_risk(self) -> None:
        assert (
            required_levels_for(
                policy=ApprovalPolicy.RISK_BASED,
                risk_level=RiskLevel.LOW,
                minimum_approvals_high_risk=3,
            )
            == 1
        )

    def test_risk_based_treats_unassessed_as_high_risk(self) -> None:
        assert (
            required_levels_for(
                policy=ApprovalPolicy.RISK_BASED,
                risk_level=None,
                minimum_approvals_high_risk=2,
            )
            == 2
        )

    @pytest.mark.parametrize("policy", [ApprovalPolicy.MULTI_LEVEL, ApprovalPolicy.ROLE_BASED])
    def test_multi_level_and_role_based_default_to_two(self, policy: ApprovalPolicy) -> None:
        assert (
            required_levels_for(
                policy=policy, risk_level=RiskLevel.LOW, minimum_approvals_high_risk=5
            )
            == 2
        )


def test_steps_at_level_filters_correctly() -> None:
    steps = [_step(1, ApprovalStatus.APPROVED), _step(2, ApprovalStatus.PENDING)]
    assert steps_at_level(steps, 1) == [steps[0]]
