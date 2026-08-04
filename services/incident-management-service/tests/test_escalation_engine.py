"""The escalation ladder: policy construction, due rungs, manual overrides."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.escalation.engine import (
    EscalationPolicy,
    EscalationStep,
    default_policy_for,
    due_steps,
    manual_step,
    next_step,
    priority_outranks,
)
from app.models.enums import EscalationTrigger, IncidentPriority


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 3, hour, minute, tzinfo=UTC)


class TestEscalationStep:
    def test_a_step_needs_a_target(self) -> None:
        with pytest.raises(ValueError, match="neither a role nor a person"):
            EscalationStep(level=1, after_minutes=15)

    def test_a_step_needs_a_positive_level(self) -> None:
        with pytest.raises(ValueError, match="level must be"):
            EscalationStep(level=0, after_minutes=15, target_role="on-call")

    def test_a_step_needs_non_negative_delay(self) -> None:
        with pytest.raises(ValueError, match="after_minutes must be"):
            EscalationStep(level=1, after_minutes=-5, target_role="on-call")


class TestEscalationPolicy:
    def test_a_policy_needs_at_least_one_step(self) -> None:
        with pytest.raises(ValueError, match="no steps"):
            EscalationPolicy(priority=IncidentPriority.P1_CRITICAL, steps=())

    def test_levels_must_be_strictly_increasing(self) -> None:
        with pytest.raises(ValueError, match="out-of-order or duplicate"):
            EscalationPolicy(
                priority=IncidentPriority.P1_CRITICAL,
                steps=(
                    EscalationStep(level=2, after_minutes=15, target_role="a"),
                    EscalationStep(level=1, after_minutes=30, target_role="b"),
                ),
            )

    def test_duplicate_levels_are_refused(self) -> None:
        with pytest.raises(ValueError, match="out-of-order or duplicate"):
            EscalationPolicy(
                priority=IncidentPriority.P1_CRITICAL,
                steps=(
                    EscalationStep(level=1, after_minutes=15, target_role="a"),
                    EscalationStep(level=1, after_minutes=30, target_role="b"),
                ),
            )

    def test_delays_must_be_non_decreasing(self) -> None:
        # A ladder that fires level 2 before level 1's own delay has
        # elapsed would make "which rung have we reached" ambiguous.
        with pytest.raises(ValueError, match="out-of-order delays"):
            EscalationPolicy(
                priority=IncidentPriority.P1_CRITICAL,
                steps=(
                    EscalationStep(level=1, after_minutes=30, target_role="a"),
                    EscalationStep(level=2, after_minutes=15, target_role="b"),
                ),
            )

    def test_step_at_finds_an_existing_level(self) -> None:
        policy = default_policy_for(IncidentPriority.P1_CRITICAL)
        assert policy.step_at(1) is not None
        assert policy.step_at(99) is None

    def test_max_level_is_the_last_step(self) -> None:
        policy = default_policy_for(IncidentPriority.P1_CRITICAL, max_levels=3)
        assert policy.max_level == 3


class TestDefaultPolicy:
    def test_a_p1_escalates_faster_than_a_p3(self) -> None:
        p1 = default_policy_for(IncidentPriority.P1_CRITICAL)
        p3 = default_policy_for(IncidentPriority.P3_MEDIUM)
        assert p1.steps[0].after_minutes < p3.steps[0].after_minutes

    def test_the_final_rung_is_always_executive(self) -> None:
        # An incident nobody has resolved by the top of its own ladder
        # needs the person who can reallocate people to it.
        policy = default_policy_for(IncidentPriority.P1_CRITICAL, max_levels=3)
        assert policy.steps[-1].target_role == "role:executive"

    def test_max_levels_is_respected(self) -> None:
        policy = default_policy_for(IncidentPriority.P1_CRITICAL, max_levels=1)
        assert len(policy.steps) == 1

    def test_every_priority_produces_a_valid_policy(self) -> None:
        # Constructing each one exercises EscalationPolicy's own
        # validation; a spacing table entry that produced an invalid
        # ladder would fail here rather than at the first real incident.
        for priority in IncidentPriority:
            default_policy_for(priority)


class TestDueSteps:
    def test_nothing_is_due_before_the_anchor(self) -> None:
        policy = default_policy_for(IncidentPriority.P1_CRITICAL)
        assert due_steps(policy, anchor=at(10), now=at(9), already_fired_levels=frozenset()) == []

    def test_a_step_becomes_due_at_its_delay(self) -> None:
        policy = default_policy_for(IncidentPriority.P1_CRITICAL)  # 15/30/45
        due = due_steps(policy, anchor=at(10), now=at(10, 15), already_fired_levels=frozenset())
        assert [one.level for one in due] == [1]

    def test_a_delayed_sweep_catches_up_every_overdue_rung_at_once(self) -> None:
        # A worker restart or missed tick must not escalate one level
        # per sweep and take several cycles to catch up.
        policy = default_policy_for(IncidentPriority.P1_CRITICAL)  # 15/30/45
        due = due_steps(policy, anchor=at(10), now=at(11), already_fired_levels=frozenset())
        assert [one.level for one in due] == [1, 2, 3]

    def test_already_fired_levels_are_excluded(self) -> None:
        policy = default_policy_for(IncidentPriority.P1_CRITICAL)
        due = due_steps(policy, anchor=at(10), now=at(11), already_fired_levels=frozenset({1, 2}))
        assert [one.level for one in due] == [3]

    def test_everything_already_fired_yields_nothing(self) -> None:
        policy = default_policy_for(IncidentPriority.P1_CRITICAL)
        due = due_steps(
            policy, anchor=at(10), now=at(11), already_fired_levels=frozenset({1, 2, 3})
        )
        assert due == []


class TestNextStep:
    def test_next_step_is_one_level_past_current(self) -> None:
        policy = default_policy_for(IncidentPriority.P1_CRITICAL, max_levels=3)
        assert next_step(policy, current_level=1).level == 2  # type: ignore[union-attr]

    def test_next_step_at_the_ceiling_is_none(self) -> None:
        policy = default_policy_for(IncidentPriority.P1_CRITICAL, max_levels=3)
        assert next_step(policy, current_level=3) is None


class TestManualStep:
    def test_a_manual_step_fires_immediately_and_names_its_target(self) -> None:
        step = manual_step(level=1, target_id="user-42", reason="Vendor needs to be looped in now.")
        assert step.after_minutes == 0
        assert step.target_id == "user-42"
        assert step.trigger is EscalationTrigger.MANUAL


class TestPriorityOutranks:
    def test_p1_outranks_the_p2_threshold(self) -> None:
        assert priority_outranks(IncidentPriority.P1_CRITICAL, IncidentPriority.P2_HIGH) is True

    def test_p3_does_not_outrank_the_p2_threshold(self) -> None:
        assert priority_outranks(IncidentPriority.P3_MEDIUM, IncidentPriority.P2_HIGH) is False

    def test_equal_priority_counts_as_meeting_the_threshold(self) -> None:
        assert priority_outranks(IncidentPriority.P2_HIGH, IncidentPriority.P2_HIGH) is True
