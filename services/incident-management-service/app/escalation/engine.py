"""The escalation ladder: who gets paged next, and when.

Pure: takes a policy and a moment, returns which rungs are due. Nothing
here reads a database or sends a page -- that is
``app/services/escalation.py``'s job, and keeping the two separated is
what makes "would this policy have escalated at 03:00 last Tuesday" a
question this module can answer without a database to ask.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.models.enums import PRIORITY_ORDER, EscalationTrigger, IncidentPriority


@dataclass(frozen=True, slots=True)
class EscalationStep:
    """One rung of an escalation ladder."""

    level: int
    after_minutes: int
    """Minutes past the anchor (an SLA's due time, or its breach time)
    before this rung fires."""

    target_role: str | None = None
    target_id: str | None = None
    trigger: EscalationTrigger = EscalationTrigger.TIME_BASED

    def __post_init__(self) -> None:
        if self.level < 1:
            raise ValueError(f"level must be >= 1, got {self.level!r}.")
        if self.after_minutes < 0:
            raise ValueError(f"after_minutes must be >= 0, got {self.after_minutes!r}.")
        if self.target_role is None and self.target_id is None:
            raise ValueError(f"Step at level {self.level} names neither a role nor a person.")


@dataclass(frozen=True, slots=True)
class EscalationPolicy:
    """An ordered ladder for one priority level.

    Steps are validated to be strictly increasing in both level and
    delay at construction -- a ladder that could loop back to an earlier
    level, or fire two rungs in the wrong order, would make "which rung
    have we reached" ambiguous exactly when an incident is already
    escalating.
    """

    priority: IncidentPriority
    steps: tuple[EscalationStep, ...]

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError(f"Policy for {self.priority} has no steps.")
        levels = [one.level for one in self.steps]
        if levels != sorted(levels) or len(levels) != len(set(levels)):
            raise ValueError(f"Policy for {self.priority} has out-of-order or duplicate levels.")
        delays = [one.after_minutes for one in self.steps]
        if delays != sorted(delays):
            raise ValueError(f"Policy for {self.priority} has out-of-order delays.")

    def step_at(self, level: int) -> EscalationStep | None:
        """The step for one level, or ``None`` if it does not exist."""
        return next((one for one in self.steps if one.level == level), None)

    @property
    def max_level(self) -> int:
        """The highest rung this ladder reaches."""
        return self.steps[-1].level


def default_policy_for(priority: IncidentPriority, *, max_levels: int = 3) -> EscalationPolicy:
    """A sensible default ladder, scaled by priority.

    A P1 escalates every 15 minutes past breach; lower priorities give
    more room before the next page, on the theory that a P4 does not
    need three people paged in the first hour the way a P1 does. The
    final rung is always ``executive`` -- an incident nobody has
    resolved by the top of its own ladder needs the person who can
    actually reallocate people to it, not a fourth engineer.
    """
    spacing = {
        IncidentPriority.P1_CRITICAL: 15,
        IncidentPriority.P2_HIGH: 30,
        IncidentPriority.P3_MEDIUM: 60,
        IncidentPriority.P4_LOW: 240,
        IncidentPriority.P5_INFORMATIONAL: 480,
    }[priority]
    roles = ["role:on-call", "role:manager", "role:executive"]
    steps = tuple(
        EscalationStep(
            level=index + 1,
            after_minutes=spacing * (index + 1),
            target_role=roles[min(index, len(roles) - 1)],
        )
        for index in range(max(1, min(max_levels, len(roles))))
    )
    return EscalationPolicy(priority=priority, steps=steps)


def due_steps(
    policy: EscalationPolicy,
    *,
    anchor: datetime,
    now: datetime,
    already_fired_levels: frozenset[int],
) -> list[EscalationStep]:
    """Every rung whose time has come and has not already fired.

    Returns every overdue step, not just the next one, so a sweep that
    was delayed -- a worker restart, a missed tick -- catches up in one
    pass rather than escalating one level per sweep and taking several
    cycles to reach where the policy actually says the incident should
    be by now.
    """
    if now < anchor:
        return []
    elapsed_minutes = (now - anchor).total_seconds() / 60.0
    return [
        step
        for step in policy.steps
        if step.level not in already_fired_levels and elapsed_minutes >= step.after_minutes
    ]


def next_step(policy: EscalationPolicy, *, current_level: int) -> EscalationStep | None:
    """The step one level past *current_level*, or ``None`` at the ceiling."""
    return policy.step_at(current_level + 1)


def manual_step(*, level: int, target_id: str, reason: str) -> EscalationStep:
    """A one-off manual escalation, outside any policy ladder.

    Manual escalation exists because a policy ladder cannot anticipate
    every situation -- an engineer who knows exactly who needs to be
    paged right now should not have to wait for a scheduled rung to
    reach them.
    """
    del reason  # carried by the caller into the stored row, not the step itself
    return EscalationStep(
        level=level, after_minutes=0, target_id=target_id, trigger=EscalationTrigger.MANUAL
    )


def priority_outranks(escalated_priority: IncidentPriority, threshold: IncidentPriority) -> bool:
    """Whether an incident's priority alone justifies immediate escalation.

    Used for policy-triggered escalation -- a P1 declared at any hour
    may escalate on priority alone rather than waiting for its first
    time-based rung, because the whole point of P1 is that the fifteen
    minutes a normal ladder would wait is itself too long.
    """
    return PRIORITY_ORDER[escalated_priority] <= PRIORITY_ORDER[threshold]


__all__ = [
    "EscalationPolicy",
    "EscalationStep",
    "default_policy_for",
    "due_steps",
    "manual_step",
    "next_step",
    "priority_outranks",
]
