"""The decision engine: many policies in, one answer out.

Four steps, and the order is the design:

1. **Select candidates.** A policy applies to a request only if its
   subject/resource/action selectors admit it. Filtering first is what
   keeps decision latency independent of how much governance an
   organization has written.
2. **Evaluate each candidate's rule** against the request's attributes,
   producing a per-policy trace.
3. **Combine the matches** through
   :data:`~app.models.enums.EFFECT_PRECEDENCE` -- deny-overrides, with
   obligations ranked above permissions.
4. **Answer, with the reasoning attached.**

**Nothing here touches the database or the network.** The engine takes
already-loaded policies and an already-assembled context, which is what
makes it testable against hand-written catalogues and what makes a
simulation identical to a live decision rather than a second
implementation that drifts.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from shared_core.logging.logger import get_logger

from app.attributes.resolver import EvaluationContext
from app.models.enums import (
    DENYING_EFFECTS,
    EFFECT_PRECEDENCE,
    PERMITTING_EFFECTS,
    ActionType,
    PolicyEffect,
    ResourceType,
    SubjectType,
)
from app.rules.engine import Rule, RuleTrace, evaluate_rule, rule_from_dict

logger = get_logger("app.evaluation.engine")


@dataclass(slots=True)
class EvaluablePolicy:
    """One policy, in the shape evaluation needs.

    A plain dataclass rather than the ORM row, so the engine can be
    driven from a hand-written catalogue in a test, from published rows
    in production, and from a mix of published rows and drafts in a
    simulation -- all through the same code path.
    """

    policy_id: str
    slug: str
    name: str
    effect: PolicyEffect
    rule: Rule
    priority: int = 100
    category: str = ""
    policy_type: str = ""
    subject_types: list[str] = field(default_factory=list)
    resource_types: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    obligations: dict[str, Any] = field(default_factory=dict)
    risk_weight: float = 0.0
    is_draft: bool = False

    def applies_to(
        self, subject_type: SubjectType, resource_type: ResourceType, action: ActionType
    ) -> bool:
        """Whether this policy's selectors admit the request at all.

        An empty selector means "any". That makes a policy with no
        resource types apply everywhere, which is the only way to write
        an estate-wide rule -- the alternative reading, that empty
        matches nothing, would make a blanket deny inexpressible.
        """
        return (
            (not self.subject_types or str(subject_type) in self.subject_types)
            and (not self.resource_types or str(resource_type) in self.resource_types)
            and (not self.actions or str(action) in self.actions)
        )


@dataclass(slots=True)
class PolicyOutcome:
    """What one policy said about one request."""

    policy_id: str
    slug: str
    name: str
    effect: PolicyEffect
    matched: bool
    priority: int
    risk_weight: float
    obligations: dict[str, Any] = field(default_factory=dict)
    trace: RuleTrace | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form."""
        return {
            "policy_id": self.policy_id,
            "slug": self.slug,
            "name": self.name,
            "effect": str(self.effect),
            "matched": self.matched,
            "priority": self.priority,
            "risk_weight": self.risk_weight,
            "obligations": self.obligations,
            "trace": self.trace.as_dict() if self.trace is not None else None,
            "error": self.error,
        }


@dataclass(slots=True)
class Decision:
    """The engine's answer, with everything needed to justify it."""

    effect: PolicyEffect = PolicyEffect.DENY
    reason: str = ""
    outcomes: list[PolicyOutcome] = field(default_factory=list)
    deciding_policy_id: str | None = None
    risk_score: float = 0.0
    obligations: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    policies_considered: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def permitted(self) -> bool:
        """Whether the caller may proceed **now**.

        Narrow deliberately: ``REQUIRE_APPROVAL`` and ``REQUIRE_MFA`` are
        not permits. Treating an obligation as permission is precisely
        how an approval gate stops existing without anyone changing a
        policy.
        """
        return self.effect in PERMITTING_EFFECTS

    @property
    def denied(self) -> bool:
        """Whether the request was refused outright."""
        return self.effect in DENYING_EFFECTS

    @property
    def matched_policy_ids(self) -> list[str]:
        """Every policy whose rule matched, in precedence order."""
        return [one.policy_id for one in self.outcomes if one.matched]

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for an API response."""
        return {
            "effect": str(self.effect),
            "permitted": self.permitted,
            "denied": self.denied,
            "reason": self.reason,
            "deciding_policy_id": self.deciding_policy_id,
            "matched_policy_ids": self.matched_policy_ids,
            "risk_score": round(self.risk_score, 4),
            "obligations": self.obligations,
            "duration_ms": round(self.duration_ms, 3),
            "policies_considered": self.policies_considered,
            "errors": self.errors,
            "trace": [one.as_dict() for one in self.outcomes],
        }


def select_candidates(
    policies: list[EvaluablePolicy],
    *,
    subject_type: SubjectType,
    resource_type: ResourceType,
    action: ActionType,
) -> list[EvaluablePolicy]:
    """Narrow a catalogue to the policies that could apply.

    Sorted by descending priority so that, among policies sharing an
    effect, the highest-priority one is the first match encountered --
    which is what makes ``deciding_policy_id`` stable rather than
    dependent on database row order.
    """
    candidates = [one for one in policies if one.applies_to(subject_type, resource_type, action)]
    candidates.sort(key=lambda one: (-one.priority, one.slug))
    return candidates


def evaluate_policy(policy: EvaluablePolicy, context: EvaluationContext) -> PolicyOutcome:
    """Evaluate one policy's rule against a context.

    An exception here is caught and recorded rather than propagated. A
    single unusable policy must not fail the whole decision -- but it
    must also not silently disappear, so the outcome carries the error
    and the caller decides what a broken policy means (see
    :func:`combine`, which treats it as a reason to refuse when the
    deployment is configured to fail closed).
    """
    try:
        matched, trace = evaluate_rule(policy.rule, context)
    except Exception as exc:
        logger.warning(
            "A policy could not be evaluated; it is recorded as an error rather than "
            "silently skipped.",
            extra={"extra_fields": {"policy_id": policy.policy_id, "error": str(exc)}},
        )
        return PolicyOutcome(
            policy_id=policy.policy_id,
            slug=policy.slug,
            name=policy.name,
            effect=policy.effect,
            matched=False,
            priority=policy.priority,
            risk_weight=policy.risk_weight,
            error=str(exc),
        )

    return PolicyOutcome(
        policy_id=policy.policy_id,
        slug=policy.slug,
        name=policy.name,
        effect=policy.effect,
        matched=matched,
        priority=policy.priority,
        risk_weight=policy.risk_weight,
        obligations=dict(policy.obligations),
        trace=trace,
    )


def combine(
    outcomes: list[PolicyOutcome],
    *,
    default_effect: PolicyEffect = PolicyEffect.DENY,
    fail_closed: bool = True,
) -> tuple[PolicyEffect, str, str | None]:
    """Reduce many matched policies to one effect.

    Returns ``(effect, reason, deciding_policy_id)``.

    The combining algorithm is deny-overrides by
    :data:`~app.models.enums.EFFECT_PRECEDENCE`, with two things worth
    stating plainly:

    - **A policy that failed to evaluate is not a policy that did not
      match.** Under ``fail_closed`` an evaluation error produces
      ``DEFERRED``, because answering "allow" on the basis of a rule
      nobody could run is the worst available outcome and answering
      "deny" would misreport a broken policy as a deliberate refusal.
    - **No match is not the same as no policies.** Both fall through to
      *default_effect*, but the reason distinguishes them, because "no
      governance is written for this" and "governance exists and none of
      it applied" call for very different responses.
    """
    errored = [one for one in outcomes if one.error is not None]
    if errored and fail_closed:
        first = errored[0]
        return (
            PolicyEffect.DEFERRED,
            (
                f"{len(errored)} polic{'y' if len(errored) == 1 else 'ies'} could not be "
                f"evaluated (first: {first.slug!r} -- {first.error}). The deployment is "
                "configured to fail closed, so no decision was reached."
            ),
            None,
        )

    matched = [one for one in outcomes if one.matched]
    if not matched:
        reason = (
            "No policy matched this request."
            if outcomes
            else "No policy applies to this subject, resource, and action."
        )
        return default_effect, f"{reason} Defaulting to {default_effect!s}.", None

    winner = max(
        matched,
        key=lambda one: (EFFECT_PRECEDENCE[one.effect], one.priority),
    )
    others = len(matched) - 1
    reason = f"Policy {winner.slug!r} applied {winner.effect!s}."
    if others:
        reason += (
            f" {others} other polic{'y' if others == 1 else 'ies'} also matched; "
            f"{winner.effect!s} takes precedence."
        )
    return winner.effect, reason, winner.policy_id


def _risk_score(outcomes: list[PolicyOutcome]) -> float:
    """Overall risk for a decision, 0.0-1.0.

    The **maximum** matched weight, not the sum. A sum grows with how
    many policies happen to overlap on a request, so a well-governed
    resource covered by six rules would score riskier than an ungoverned
    one covered by none -- the exact inversion of what the number is
    for. The same reasoning the knowledge graph applies to blast radius.
    """
    weights = [one.risk_weight for one in outcomes if one.matched]
    return round(min(1.0, max(weights)), 4) if weights else 0.0


def evaluate(
    policies: list[EvaluablePolicy],
    context: EvaluationContext,
    *,
    subject_type: SubjectType,
    resource_type: ResourceType,
    action: ActionType,
    default_effect: PolicyEffect = PolicyEffect.DENY,
    fail_closed: bool = True,
    max_policies: int = 500,
) -> Decision:
    """Decide one request against a catalogue.

    Pure: no database, no network, no clock beyond timing itself. That
    is what lets a simulation reuse this exact function rather than a
    parallel implementation that drifts away from the live one.
    """
    started = time.perf_counter()
    candidates = select_candidates(
        policies,
        subject_type=subject_type,
        resource_type=resource_type,
        action=action,
    )

    truncated = False
    if len(candidates) > max_policies:
        # Truncation is reported, never silent. A decision made from a
        # partial catalogue is one whose "no policy denied this" cannot
        # be trusted, and a caller has to be able to see that.
        truncated = True
        candidates = candidates[:max_policies]

    outcomes = [evaluate_policy(one, context) for one in candidates]
    effect, reason, deciding = combine(
        outcomes, default_effect=default_effect, fail_closed=fail_closed
    )

    decision = Decision(
        effect=effect,
        reason=reason,
        outcomes=outcomes,
        deciding_policy_id=deciding,
        risk_score=_risk_score(outcomes),
        policies_considered=len(candidates),
        errors=[one.error for one in outcomes if one.error is not None],
        duration_ms=(time.perf_counter() - started) * 1000,
    )

    if deciding is not None:
        winner = next(one for one in outcomes if one.policy_id == deciding)
        decision.obligations = dict(winner.obligations)

    if truncated:
        note = (
            f"Only the {max_policies} highest-priority applicable policies were "
            "evaluated; this decision may not reflect the whole catalogue."
        )
        decision.errors.append(note)
        decision.reason = f"{decision.reason} {note}"

    return decision


def policy_from_row(row: Any, *, is_draft: bool = False) -> EvaluablePolicy:
    """Build an :class:`EvaluablePolicy` from a stored policy row.

    Raises:
        ValidationError: If the stored rule cannot be rebuilt. Loud
            rather than lenient -- a policy whose rule will not parse
            must not quietly evaluate as "no match", which is
            indistinguishable from a policy that decided not to apply.
    """
    return EvaluablePolicy(
        policy_id=str(row.id),
        slug=row.slug,
        name=row.name,
        effect=PolicyEffect(str(row.effect)),
        rule=rule_from_dict(row.compiled_rule or {}, name=row.slug),
        priority=row.priority,
        category=str(row.category),
        policy_type=str(row.policy_type),
        subject_types=list(row.subject_types or []),
        resource_types=list(row.resource_types or []),
        actions=list(row.actions or []),
        obligations=dict(row.obligations or {}),
        risk_weight=float(row.risk_weight or 0.0),
        is_draft=is_draft,
    )


__all__ = [
    "Decision",
    "EvaluablePolicy",
    "PolicyOutcome",
    "combine",
    "evaluate",
    "evaluate_policy",
    "policy_from_row",
    "select_candidates",
]
