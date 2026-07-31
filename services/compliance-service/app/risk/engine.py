"""Risk scoring and finding identity.

Two pure concerns that share a property: both produce a number or a
string that other systems key on, so both have to be stable across runs.

**Fingerprinting is here rather than in the assessment engine** because
it is the thing that decides whether a re-detection is the same problem
or a new one -- and getting that wrong is what turns a compliance
programme into a queue nobody works. 365 findings for one unpatched host
is not a backlog, it is noise, and the age of the original finding --
the only number that makes an overdue problem visible -- is lost in it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.models.enums import (
    IMPACT_VALUES,
    LIKELIHOOD_VALUES,
    FindingSeverity,
    RiskImpact,
    RiskLikelihood,
    RiskSeverity,
    severity_for,
)

MAX_RISK_SCORE = 25.0
"""The top of the 5x5 matrix: ``almost_certain`` x ``severe``."""


@dataclass(slots=True)
class RiskAssessment:
    """A likelihood/impact pair scored and banded."""

    likelihood: RiskLikelihood
    impact: RiskImpact
    severity: RiskSeverity
    score: float
    normalised: float
    """The score on a 0-100 scale, for putting beside compliance scores.

    Kept separate from :attr:`score` rather than replacing it: risk
    people read the 5x5 matrix value and would not recognise a 68, while
    an executive summary that mixes a 17 with a 94 is unreadable.
    """


def assess(likelihood: RiskLikelihood, impact: RiskImpact) -> RiskAssessment:
    """Score and band a risk. Never accepts a severity as input."""
    score = float(LIKELIHOOD_VALUES[likelihood] * IMPACT_VALUES[impact])
    return RiskAssessment(
        likelihood=likelihood,
        impact=impact,
        severity=severity_for(likelihood, impact),
        score=score,
        normalised=round(score / MAX_RISK_SCORE * 100.0, 2),
    )


def residual(likelihood: RiskLikelihood | None, impact: RiskImpact | None) -> RiskAssessment | None:
    """Score the risk left after mitigation, if both halves are known.

    Returns ``None`` when either is missing rather than assuming the
    inherent value. Silently carrying the inherent likelihood forward
    would report a mitigation as having reduced risk it never touched --
    which is the specific way risk registers come to overstate how well
    a programme is doing.
    """
    if likelihood is None or impact is None:
        return None
    return assess(likelihood, impact)


def next_reference(existing: list[str], *, prefix: str = "RISK") -> str:
    """The next human-quotable reference in a sequence.

    Derived from the highest existing number rather than from a count,
    so deleting an entry does not cause the next one to reuse a
    reference that is already written down in somebody's meeting notes.
    """
    highest = 0
    for one in existing:
        _, _, tail = one.rpartition("-")
        if tail.isdigit():
            highest = max(highest, int(tail))
    return f"{prefix}-{highest + 1:04d}"


def fingerprint(
    *,
    control_id: str,
    target_id: str | None,
    target_type: str | None = None,
    qualifier: str | None = None,
) -> str:
    """A stable identity for "this same problem, on this same thing".

    Deliberately **excludes** the assessment id, the timestamp, and the
    observed values. Including any of them would make every run produce
    new findings, which is the failure this exists to prevent. Including
    the observed values is the subtle one: a host whose patch level
    changes from 4.1 to 4.2 while still being out of date is the same
    unresolved problem, and re-raising it would reset an age somebody is
    being measured on.
    """
    parts = [control_id, target_type or "", target_id or "", qualifier or ""]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def risk_score_for_finding(severity: FindingSeverity, *, detection_count: int = 1) -> float:
    """A 0-100 urgency number for one finding.

    Severity dominates; recurrence adds a bounded amount. A medium
    finding detected two hundred times is a real problem and should
    outrank a medium detected once -- but it must never outrank a
    critical, because "how often" is not "how bad" and a queue sorted
    the other way sends people to the wrong fire.
    """
    base = {
        FindingSeverity.CRITICAL: 90.0,
        FindingSeverity.HIGH: 70.0,
        FindingSeverity.MEDIUM: 45.0,
        FindingSeverity.LOW: 20.0,
        FindingSeverity.INFORMATIONAL: 5.0,
    }[severity]
    recurrence = min(9.0, max(0, detection_count - 1) * 0.5)
    return round(min(99.0, base + recurrence), 2)


def due_at(
    severity: FindingSeverity,
    *,
    detected_at: datetime,
    critical_days: int = 7,
    high_days: int = 30,
    medium_days: int = 90,
    low_days: int = 180,
) -> datetime | None:
    """When a finding of this severity should be fixed by.

    Informational findings get no due date, on purpose. A deadline
    attached to something nobody is expected to act on manufactures an
    overdue queue, and an overdue queue full of things that do not
    matter is how people learn to ignore the ones that do.
    """
    days = {
        FindingSeverity.CRITICAL: critical_days,
        FindingSeverity.HIGH: high_days,
        FindingSeverity.MEDIUM: medium_days,
        FindingSeverity.LOW: low_days,
    }.get(severity)
    return None if days is None else detected_at + timedelta(days=days)


def is_overdue(due: datetime | None, *, now: datetime | None = None) -> bool:
    """Whether a due date has passed."""
    if due is None:
        return False
    moment = now or datetime.now(UTC)
    return due < moment


def next_review(
    *, last_reviewed: datetime | None, interval_days: int, created_at: datetime
) -> datetime:
    """When something is next due for review.

    Measured from the last review, or from creation if there has never
    been one -- so a risk registered a year ago and never looked at is
    immediately overdue rather than being given a fresh window by the
    act of asking.
    """
    anchor = last_reviewed or created_at
    return anchor + timedelta(days=interval_days)


__all__ = [
    "MAX_RISK_SCORE",
    "RiskAssessment",
    "assess",
    "due_at",
    "fingerprint",
    "is_overdue",
    "next_reference",
    "next_review",
    "residual",
    "risk_score_for_finding",
]
