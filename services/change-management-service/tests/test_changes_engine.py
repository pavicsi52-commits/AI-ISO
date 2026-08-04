"""The change lifecycle: legal transitions, CAB eligibility, durations.

Pure -- no fixtures, no database.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from shared_core.exceptions.validation import ValidationError

from app.changes.engine import (
    ALLOWED_TRANSITIONS,
    compute_durations,
    is_emergency,
    requires_cab_review,
    validate_transition,
)
from app.models.enums import ChangeStatus, ChangeType, RiskLevel


class TestTransitions:
    def test_draft_can_move_to_submitted(self) -> None:
        validate_transition(ChangeStatus.DRAFT, ChangeStatus.SUBMITTED)

    def test_draft_cannot_jump_to_scheduled(self) -> None:
        with pytest.raises(ValidationError):
            validate_transition(ChangeStatus.DRAFT, ChangeStatus.SCHEDULED)

    def test_submitted_can_move_back_to_draft(self) -> None:
        validate_transition(ChangeStatus.SUBMITTED, ChangeStatus.DRAFT)

    def test_pending_approval_can_route_through_cab_or_directly_to_scheduled(self) -> None:
        validate_transition(ChangeStatus.PENDING_APPROVAL, ChangeStatus.CAB_REVIEW)
        validate_transition(ChangeStatus.PENDING_APPROVAL, ChangeStatus.SCHEDULED)

    @pytest.mark.parametrize(
        "dead_end", [ChangeStatus.CANCELLED, ChangeStatus.REJECTED, ChangeStatus.CLOSED]
    )
    def test_cancelled_rejected_and_closed_are_true_dead_ends(self, dead_end: ChangeStatus) -> None:
        assert ALLOWED_TRANSITIONS[dead_end] == frozenset()

    def test_cancelled_refuses_every_move(self) -> None:
        for target in ChangeStatus:
            if target is ChangeStatus.CANCELLED:
                continue
            with pytest.raises(ValidationError):
                validate_transition(ChangeStatus.CANCELLED, target)

    def test_every_status_has_a_transition_table_entry(self) -> None:
        for status in ChangeStatus:
            assert status in ALLOWED_TRANSITIONS

    def test_completed_and_rolled_back_both_lead_only_to_closed(self) -> None:
        assert ALLOWED_TRANSITIONS[ChangeStatus.COMPLETED] == frozenset({ChangeStatus.CLOSED})
        assert ALLOWED_TRANSITIONS[ChangeStatus.ROLLED_BACK] == frozenset({ChangeStatus.CLOSED})

    def test_the_error_names_what_is_actually_allowed(self) -> None:
        with pytest.raises(ValidationError, match="submitted"):
            validate_transition(ChangeStatus.DRAFT, ChangeStatus.CLOSED)


class TestIsEmergency:
    def test_emergency_type_is_emergency(self) -> None:
        assert is_emergency(ChangeType.EMERGENCY) is True

    @pytest.mark.parametrize(
        "change_type", [ChangeType.STANDARD, ChangeType.NORMAL, ChangeType.EXPEDITED]
    )
    def test_every_other_type_is_not_emergency(self, change_type: ChangeType) -> None:
        assert is_emergency(change_type) is False


class TestRequiresCabReview:
    def test_standard_change_never_requires_cab_by_default(self) -> None:
        assert (
            requires_cab_review(
                risk_level=RiskLevel.CRITICAL,
                change_type=ChangeType.STANDARD,
                standard_change_requires_cab=False,
            )
            is False
        )

    def test_standard_change_can_be_opted_back_into_cab(self) -> None:
        assert (
            requires_cab_review(
                risk_level=RiskLevel.LOW,
                change_type=ChangeType.STANDARD,
                standard_change_requires_cab=True,
            )
            is True
        )

    def test_emergency_change_never_requires_cab(self) -> None:
        assert (
            requires_cab_review(
                risk_level=RiskLevel.CRITICAL,
                change_type=ChangeType.EMERGENCY,
                standard_change_requires_cab=False,
            )
            is False
        )

    @pytest.mark.parametrize("risk_level", [RiskLevel.HIGH, RiskLevel.CRITICAL])
    def test_normal_change_requires_cab_above_medium_risk(self, risk_level: RiskLevel) -> None:
        assert (
            requires_cab_review(
                risk_level=risk_level,
                change_type=ChangeType.NORMAL,
                standard_change_requires_cab=False,
            )
            is True
        )

    @pytest.mark.parametrize("risk_level", [RiskLevel.LOW, RiskLevel.MEDIUM])
    def test_normal_change_does_not_require_cab_at_or_below_medium_risk(
        self, risk_level: RiskLevel
    ) -> None:
        assert (
            requires_cab_review(
                risk_level=risk_level,
                change_type=ChangeType.NORMAL,
                standard_change_requires_cab=False,
            )
            is False
        )

    def test_an_unassessed_change_requires_cab(self) -> None:
        # Absence of an assessment is not evidence of low risk -- a
        # change must not be able to skip CAB by skipping assessment.
        assert (
            requires_cab_review(
                risk_level=None, change_type=ChangeType.NORMAL, standard_change_requires_cab=False
            )
            is True
        )


class TestComputeDurations:
    def test_both_none_before_either_moment_is_known(self) -> None:
        durations = compute_durations(
            submitted_at=None, approved_at=None, actual_start_at=None, actual_end_at=None
        )
        assert durations.approval_duration_seconds is None
        assert durations.implementation_duration_seconds is None

    def test_approval_duration_is_none_while_still_pending(self) -> None:
        submitted = datetime(2026, 1, 1, tzinfo=UTC)
        durations = compute_durations(
            submitted_at=submitted, approved_at=None, actual_start_at=None, actual_end_at=None
        )
        assert durations.approval_duration_seconds is None

    def test_approval_duration_computes_once_both_moments_are_known(self) -> None:
        submitted = datetime(2026, 1, 1, tzinfo=UTC)
        approved = submitted + timedelta(hours=3)
        durations = compute_durations(
            submitted_at=submitted, approved_at=approved, actual_start_at=None, actual_end_at=None
        )
        assert durations.approval_duration_seconds == pytest.approx(3 * 3600)

    def test_implementation_duration_computes_once_both_moments_are_known(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=UTC)
        end = start + timedelta(minutes=90)
        durations = compute_durations(
            submitted_at=None, approved_at=None, actual_start_at=start, actual_end_at=end
        )
        assert durations.implementation_duration_seconds == pytest.approx(90 * 60)
