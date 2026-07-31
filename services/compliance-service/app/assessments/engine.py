"""Turning control rules and collected evidence into verdicts.

Pure, like ``app/rules/engine.py``: this module takes prepared inputs
and returns results. Everything that reads a database, calls another
service, or looks at a clock lives in ``app/services/assessment.py``.

The separation is what makes an assessment reproducible. Given the same
controls, the same evidence, and the same waivers, this module returns
the same verdicts -- which is the property an auditor is actually
relying on when they ask you to re-run last quarter's assessment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from app.models.enums import (
    FINDING_SEVERITY_FOR_CONTROL,
    ControlSeverity,
    ControlStatus,
    FindingSeverity,
    ResultStatus,
)
from app.rules.engine import (
    Rule,
    RuleOutcome,
    describe_failures,
    evaluate_rule,
    rule_from_dict,
)


@dataclass(slots=True)
class EvaluableControl:
    """A control in the form the engine needs, with no ORM attached."""

    control_id: str
    framework_id: str | None
    code: str
    title: str
    severity: ControlSeverity
    status: ControlStatus
    is_automatable: bool
    rule: Rule | None
    category: str = "other"
    remediation_guidance: str | None = None

    @property
    def weightless(self) -> bool:
        """Whether this control contributes nothing to a score."""
        return self.severity is ControlSeverity.INFORMATIONAL


@dataclass(slots=True)
class Target:
    """One thing a control is evaluated against, and what is known about it."""

    target_id: str
    target_type: str
    name: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    """The collected evidence for this target, as a flat-ish document.

    Empty is meaningful and is *not* treated as compliant -- see
    :func:`evaluate_control`.
    """

    evidence_id: str | None = None


@dataclass(slots=True)
class Waiver:
    """An approved exception, in the form the engine needs."""

    exception_id: str
    control_id: str
    target_id: str | None = None
    expires_at: datetime | None = None

    def covers(self, control_id: str, target_id: str | None, *, now: datetime) -> bool:
        """Whether this waiver excuses a failure here and now.

        A waiver with no ``target_id`` covers every target of its
        control -- deliberately broad, and exactly why it still expires
        and is still counted every time it is relied on.
        """
        if self.control_id != control_id:
            return False
        if self.expires_at is not None and self.expires_at <= now:
            return False
        return self.target_id is None or self.target_id == target_id


@dataclass(slots=True)
class ControlResult:
    """One control's verdict on one target."""

    control_id: str
    framework_id: str | None
    status: ResultStatus
    reason: str
    target_id: str | None = None
    target_type: str | None = None
    target_name: str | None = None
    expected: dict[str, Any] = field(default_factory=dict)
    observed: dict[str, Any] = field(default_factory=dict)
    evidence_id: str | None = None
    exception_id: str | None = None
    severity: ControlSeverity = ControlSeverity.MEDIUM
    error: str | None = None

    @property
    def is_failure(self) -> bool:
        """Whether this result should raise a finding."""
        return self.status in (ResultStatus.FAIL, ResultStatus.WARNING)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form."""
        return {
            "control_id": self.control_id,
            "framework_id": self.framework_id,
            "status": str(self.status),
            "reason": self.reason,
            "target_id": self.target_id,
            "target_type": self.target_type,
            "severity": str(self.severity),
            "exception_id": self.exception_id,
        }


@dataclass(slots=True)
class AssessmentOutcome:
    """Everything one assessment run decided."""

    results: list[ControlResult] = field(default_factory=list)
    controls_evaluated: int = 0
    truncated: bool = False
    """Whether a ceiling stopped the run short.

    Reported rather than hidden, because a partial assessment presented
    as a complete one is worse than no assessment: it produces a score
    for a fraction of the estate and prints it next to the word
    "compliant".
    """

    truncation_reason: str | None = None

    def counts(self) -> dict[str, int]:
        """How many results landed in each status."""
        tally: dict[str, int] = {str(one): 0 for one in ResultStatus}
        for result in self.results:
            tally[str(result.status)] += 1
        return tally

    def failures(self) -> list[ControlResult]:
        """Every result that should become a finding."""
        return [one for one in self.results if one.is_failure]


def finding_severity_for(severity: ControlSeverity) -> FindingSeverity:
    """The finding severity a control of this severity produces."""
    return FINDING_SEVERITY_FOR_CONTROL[severity]


def evaluate_control(
    control: EvaluableControl,
    target: Target,
    *,
    now: datetime,
    waivers: list[Waiver] | None = None,
) -> ControlResult:
    """Decide one control against one target.

    The order of the guards below is the whole design:

    1. **Not applicable** short-circuits everything. A control an
       organization has formally scoped out is not a failure and not an
       unknown -- it is not a requirement, and it must leave the
       denominator entirely.
    2. **Not automatable** returns ``NOT_ASSESSED``, never ``PASS``. A
       control that needs somebody to read a policy document cannot be
       satisfied by a scanner that found nothing to complain about.
    3. **No evidence** returns ``NOT_ASSESSED``, never ``PASS``. This is
       the single most important line in the module: a collector that
       silently returned nothing must not certify the host it failed to
       reach. Defaulting to pass here is how compliance tools come to
       report green estates they never inspected.
    4. Only then is the rule evaluated -- and only a *failure* consults
       the waivers, because waiving a pass is meaningless and waiving an
       error would hide a broken collector behind a business decision.
    """
    if control.status is ControlStatus.NOT_APPLICABLE:
        return ControlResult(
            control_id=control.control_id,
            framework_id=control.framework_id,
            status=ResultStatus.NOT_APPLICABLE,
            reason=f"Control {control.code} is scoped out for this organization.",
            target_id=target.target_id,
            target_type=target.target_type,
            target_name=target.name,
            severity=control.severity,
        )

    if not control.is_automatable or control.rule is None:
        return ControlResult(
            control_id=control.control_id,
            framework_id=control.framework_id,
            status=ResultStatus.NOT_ASSESSED,
            reason=(
                f"Control {control.code} is not automatable and needs a manual "
                "assessment with recorded evidence."
            ),
            target_id=target.target_id,
            target_type=target.target_type,
            target_name=target.name,
            severity=control.severity,
        )

    if not target.payload:
        return ControlResult(
            control_id=control.control_id,
            framework_id=control.framework_id,
            status=ResultStatus.NOT_ASSESSED,
            reason=(
                f"No evidence was collected for {target.target_id!r}, so control "
                f"{control.code} could not be evaluated."
            ),
            target_id=target.target_id,
            target_type=target.target_type,
            target_name=target.name,
            severity=control.severity,
            evidence_id=target.evidence_id,
        )

    outcome: RuleOutcome = evaluate_rule(control.rule, target.payload, now=now)
    if outcome.passed:
        return ControlResult(
            control_id=control.control_id,
            framework_id=control.framework_id,
            status=ResultStatus.PASS,
            reason=f"Control {control.code} is met.",
            target_id=target.target_id,
            target_type=target.target_type,
            target_name=target.name,
            observed=outcome.as_dict(),
            evidence_id=target.evidence_id,
            severity=control.severity,
        )

    covering = next(
        (
            one
            for one in (waivers or [])
            if one.covers(control.control_id, target.target_id, now=now)
        ),
        None,
    )
    if covering is not None:
        return ControlResult(
            control_id=control.control_id,
            framework_id=control.framework_id,
            status=ResultStatus.EXCEPTED,
            reason=(
                f"Control {control.code} is not met, waived by exception "
                f"{covering.exception_id}. {describe_failures(outcome)}"
            ),
            target_id=target.target_id,
            target_type=target.target_type,
            target_name=target.name,
            observed=outcome.as_dict(),
            evidence_id=target.evidence_id,
            exception_id=covering.exception_id,
            severity=control.severity,
        )

    # An informational control that fails is a WARNING rather than a
    # FAIL. It still produces a finding and still appears in reports; it
    # simply is not the sort of thing that should turn a dashboard red,
    # and calling it a failure trains people to ignore failures.
    status = ResultStatus.WARNING if control.weightless else ResultStatus.FAIL
    return ControlResult(
        control_id=control.control_id,
        framework_id=control.framework_id,
        status=status,
        reason=f"Control {control.code} is not met. {describe_failures(outcome)}",
        target_id=target.target_id,
        target_type=target.target_type,
        target_name=target.name,
        observed=outcome.as_dict(),
        evidence_id=target.evidence_id,
        severity=control.severity,
    )


def evaluate_assessment(
    controls: list[EvaluableControl],
    targets: list[Target],
    *,
    now: datetime,
    waivers: list[Waiver] | None = None,
    max_controls: int = 2_000,
    max_targets_per_control: int = 5_000,
) -> AssessmentOutcome:
    """Evaluate a whole catalogue against a whole estate.

    Both ceilings are enforced, and both are *reported* through
    :attr:`AssessmentOutcome.truncated` rather than silently applied.
    Either one alone can be satisfied while the product is still
    ruinous -- 2,000 controls across 5,000 hosts is ten million verdicts
    -- which is why there are two.

    A control with no targets is still evaluated once, against a
    null target, so an organization-wide control ("an incident response
    plan exists") produces a verdict rather than vanishing.
    """
    outcome = AssessmentOutcome()

    considered = controls[:max_controls]
    if len(controls) > max_controls:
        outcome.truncated = True
        outcome.truncation_reason = (
            f"{len(controls)} controls were in scope but the ceiling is {max_controls}; "
            f"{len(controls) - max_controls} were not evaluated."
        )

    scoped_targets = targets[:max_targets_per_control]
    if len(targets) > max_targets_per_control:
        outcome.truncated = True
        reason = (
            f"{len(targets)} targets were in scope but the ceiling is "
            f"{max_targets_per_control}; {len(targets) - max_targets_per_control} were "
            "not evaluated."
        )
        outcome.truncation_reason = (
            reason if outcome.truncation_reason is None else f"{outcome.truncation_reason} {reason}"
        )

    for control in considered:
        outcome.controls_evaluated += 1
        if not scoped_targets:
            outcome.results.append(
                evaluate_control(
                    control,
                    Target(target_id="", target_type="organization"),
                    now=now,
                    waivers=waivers,
                )
            )
            continue
        for target in scoped_targets:
            outcome.results.append(evaluate_control(control, target, now=now, waivers=waivers))

    return outcome


def control_from_row(row: Any) -> EvaluableControl:
    """Project a ``ComplianceControl`` row into an :class:`EvaluableControl`.

    Raises:
        ValidationError: Propagated from ``rule_from_dict`` if the stored
            rule names an operator that no longer exists. Loud is right:
            a control silently degrading to "no rule" would evaluate as
            ``NOT_ASSESSED`` forever while still looking configured.
    """
    stored = row.rule or {}
    rule = rule_from_dict(stored, name=row.code) if stored else None
    return EvaluableControl(
        control_id=str(row.id),
        framework_id=str(row.framework_id) if row.framework_id else None,
        code=row.code,
        title=row.title,
        severity=ControlSeverity(str(row.severity)),
        status=ControlStatus(str(row.status)),
        is_automatable=bool(row.is_automatable),
        rule=rule,
        category=str(row.category),
        remediation_guidance=row.remediation_guidance,
    )


def waiver_from_row(row: Any) -> Waiver:
    """Project a ``ComplianceException`` row into a :class:`Waiver`."""
    return Waiver(
        exception_id=str(row.id),
        control_id=str(row.control_id),
        target_id=row.target_id,
        expires_at=row.expires_at,
    )


def target_id_of(value: str | UUID | None) -> str | None:
    """Normalise a target identifier to a string, or ``None``."""
    return None if value is None else str(value)


__all__ = [
    "AssessmentOutcome",
    "ControlResult",
    "EvaluableControl",
    "Target",
    "Waiver",
    "control_from_row",
    "evaluate_assessment",
    "evaluate_control",
    "finding_severity_for",
    "target_id_of",
    "waiver_from_row",
]
