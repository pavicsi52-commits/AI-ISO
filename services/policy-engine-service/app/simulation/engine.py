"""What-if analysis, conflict detection, and impact.

**A simulation runs the live decision path.** :func:`app.evaluation.engine.evaluate`
is called with the same signature it gets in production, over a
catalogue that may include unpublished drafts. Writing a second
evaluator for previews would guarantee the two eventually disagree --
and a preview that disagrees with production is worse than no preview,
because it is trusted.

The number this exists to produce is not "how many were allowed" but
**how many outcomes changed**. Anyone can guess what a new deny does;
what nobody can guess is which of the six thousand requests a week it
quietly breaks.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from app.attributes.resolver import EvaluationContext
from app.evaluation.engine import Decision, EvaluablePolicy, evaluate
from app.models.enums import (
    DENYING_EFFECTS,
    EFFECT_PRECEDENCE,
    PERMITTING_EFFECTS,
    ActionType,
    PolicyEffect,
    ResourceType,
    SubjectType,
)
from app.rules.engine import referenced_attributes


@dataclass(slots=True)
class SimulationRequest:
    """One request to rehearse."""

    label: str
    subject_type: SubjectType
    resource_type: ResourceType
    action: ActionType
    context: EvaluationContext = field(default_factory=EvaluationContext)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form."""
        return {
            "label": self.label,
            "subject_type": str(self.subject_type),
            "resource_type": str(self.resource_type),
            "action": str(self.action),
        }


@dataclass(slots=True)
class ComparedOutcome:
    """What one request does now versus what it would do."""

    request: SimulationRequest
    baseline: Decision
    candidate: Decision

    @property
    def changed(self) -> bool:
        """Whether the effect differs between the two catalogues."""
        return self.baseline.effect is not self.candidate.effect

    @property
    def newly_denied(self) -> bool:
        """Whether something that worked would stop working.

        The single most important thing a preview can report. A change
        that turns allows into denies is a change that breaks people,
        and it is worth separating from the merely different.
        """
        return (
            self.baseline.effect in PERMITTING_EFFECTS
            and self.candidate.effect not in PERMITTING_EFFECTS
        )

    @property
    def newly_permitted(self) -> bool:
        """Whether something that was refused would start working."""
        return (
            self.baseline.effect not in PERMITTING_EFFECTS
            and self.candidate.effect in PERMITTING_EFFECTS
        )

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form."""
        return {
            "request": self.request.as_dict(),
            "before": str(self.baseline.effect),
            "after": str(self.candidate.effect),
            "changed": self.changed,
            "newly_denied": self.newly_denied,
            "newly_permitted": self.newly_permitted,
            "before_reason": self.baseline.reason,
            "after_reason": self.candidate.reason,
        }


@dataclass(slots=True)
class SimulationResult:
    """Everything one simulation found."""

    outcomes: list[ComparedOutcome] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def request_count(self) -> int:
        """How many requests were rehearsed."""
        return len(self.outcomes)

    @property
    def allowed_count(self) -> int:
        """How many the candidate catalogue permits."""
        return sum(1 for one in self.outcomes if one.candidate.effect in PERMITTING_EFFECTS)

    @property
    def denied_count(self) -> int:
        """How many the candidate catalogue refuses."""
        return sum(1 for one in self.outcomes if one.candidate.effect in DENYING_EFFECTS)

    @property
    def changed_count(self) -> int:
        """How many outcomes differ from today's."""
        return sum(1 for one in self.outcomes if one.changed)

    @property
    def newly_denied(self) -> list[ComparedOutcome]:
        """The ones that would break."""
        return [one for one in self.outcomes if one.newly_denied]

    def summarise(self) -> str:
        """A one-line account, leading with what breaks."""
        if not self.outcomes:
            return "No requests were simulated."
        breaks = len(self.newly_denied)
        parts = [
            f"{self.request_count} request(s): {self.allowed_count} allowed, "
            f"{self.denied_count} denied"
        ]
        if self.changed_count:
            parts.append(f"{self.changed_count} outcome(s) would change")
        if breaks:
            parts.append(f"**{breaks} would newly be refused**")
        if self.conflicts:
            parts.append(f"{len(self.conflicts)} policy conflict(s) detected")
        return "; ".join(parts) + "."

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form."""
        return {
            "request_count": self.request_count,
            "allowed_count": self.allowed_count,
            "denied_count": self.denied_count,
            "changed_count": self.changed_count,
            "newly_denied_count": len(self.newly_denied),
            "duration_ms": round(self.duration_ms, 3),
            "summary": self.summarise(),
            "outcomes": [one.as_dict() for one in self.outcomes],
            "conflicts": self.conflicts,
        }


def simulate(
    baseline: list[EvaluablePolicy],
    candidate: list[EvaluablePolicy],
    requests: list[SimulationRequest],
    *,
    default_effect: PolicyEffect = PolicyEffect.DENY,
    fail_closed: bool = True,
    max_policies: int = 500,
) -> SimulationResult:
    """Run every request against both catalogues and compare.

    Both sides go through the same :func:`~app.evaluation.engine.evaluate`
    the live path uses, so a preview cannot drift away from production
    behaviour without the production behaviour changing too.
    """
    started = time.perf_counter()
    outcomes: list[ComparedOutcome] = []

    for request in requests:
        shared = {
            "subject_type": request.subject_type,
            "resource_type": request.resource_type,
            "action": request.action,
            "default_effect": default_effect,
            "fail_closed": fail_closed,
            "max_policies": max_policies,
        }
        outcomes.append(
            ComparedOutcome(
                request=request,
                baseline=evaluate(baseline, request.context, **shared),  # type: ignore[arg-type]
                candidate=evaluate(candidate, request.context, **shared),  # type: ignore[arg-type]
            )
        )

    return SimulationResult(
        outcomes=outcomes,
        conflicts=detect_conflicts(candidate),
        duration_ms=(time.perf_counter() - started) * 1000,
    )


def detect_conflicts(policies: list[EvaluablePolicy]) -> list[dict[str, Any]]:
    """Find policy pairs that could contradict each other.

    A conflict is two policies with **opposing effects**, **overlapping
    selectors**, and **at least one attribute in common**. All three
    matter:

    - Opposing effects alone would flag every allow/deny pair in the
      catalogue, which is most of it.
    - Overlapping selectors alone would flag policies that can never see
      the same request.
    - The shared attribute is what makes it cheap: two policies reading
      disjoint attributes cannot disagree about one request, so the pair
      can be skipped without evaluating anything.

    This reports *potential* conflicts, and says so. Proving that two
    rule trees can both be satisfied is a satisfiability problem; the
    honest thing is to surface the pairs worth a human look rather than
    to claim more certainty than the analysis has.
    """
    conflicts: list[dict[str, Any]] = []
    attributes = {one.policy_id: referenced_attributes(one.rule) for one in policies}

    for index, left in enumerate(policies):
        for right in policies[index + 1 :]:
            if not _effects_oppose(left.effect, right.effect):
                continue
            if not _selectors_overlap(left, right):
                continue
            shared = attributes[left.policy_id] & attributes[right.policy_id]
            if not shared:
                continue
            conflicts.append(
                {
                    "policies": [left.slug, right.slug],
                    "policy_ids": [left.policy_id, right.policy_id],
                    "effects": [str(left.effect), str(right.effect)],
                    "shared_attributes": sorted(f"{source}.{path}" for source, path in shared),
                    "resolution": (
                        f"{_dominant(left, right).effect!s} would win "
                        f"({_dominant(left, right).slug!r})."
                    ),
                    "note": (
                        "Potential conflict: both could match one request. Whether they "
                        "actually do depends on values this analysis does not have."
                    ),
                }
            )
    return conflicts


def _effects_oppose(left: PolicyEffect, right: PolicyEffect) -> bool:
    """Whether two effects pull in different directions."""
    return (left in PERMITTING_EFFECTS) != (right in PERMITTING_EFFECTS)


def _selectors_overlap(left: EvaluablePolicy, right: EvaluablePolicy) -> bool:
    """Whether two policies could ever see the same request."""
    return (
        _dimension_overlaps(left.subject_types, right.subject_types)
        and _dimension_overlaps(left.resource_types, right.resource_types)
        and _dimension_overlaps(left.actions, right.actions)
    )


def _dimension_overlaps(left: list[str], right: list[str]) -> bool:
    """Whether two selector lists intersect, treating empty as "any"."""
    if not left or not right:
        return True
    return bool(set(left) & set(right))


def _dominant(left: EvaluablePolicy, right: EvaluablePolicy) -> EvaluablePolicy:
    """Which of two policies would win if both matched."""
    return max((left, right), key=lambda one: (EFFECT_PRECEDENCE[one.effect], one.priority))


def impact_of(
    baseline: list[EvaluablePolicy],
    candidate: list[EvaluablePolicy],
    requests: list[SimulationRequest],
    **kwargs: Any,
) -> dict[str, Any]:
    """Impact analysis: what a catalogue change would break.

    A thin framing over :func:`simulate` that leads with the newly
    refused, because that is the answer somebody about to publish
    actually needs.
    """
    result = simulate(baseline, candidate, requests, **kwargs)
    return {
        **result.as_dict(),
        "breaking_changes": [one.as_dict() for one in result.newly_denied],
        "safe": not result.newly_denied,
    }


__all__ = [
    "ComparedOutcome",
    "SimulationRequest",
    "SimulationResult",
    "detect_conflicts",
    "impact_of",
    "simulate",
]
