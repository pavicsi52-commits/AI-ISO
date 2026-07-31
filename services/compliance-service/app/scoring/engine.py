"""Computing compliance scores.

Pure. Takes results, returns numbers.

Two things here are worth arguing about, and both are argued in place:
what belongs in the denominator, and whether controls are weighted. Get
either wrong and the service produces a number that is confidently
incorrect -- which is worse than producing none, because a number gets
quoted in a board pack and nobody re-derives it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.enums import (
    SCORED_STATUSES,
    SEVERITY_WEIGHTS,
    ControlSeverity,
    ResultStatus,
    ScoreGrade,
    grade_for,
)

MIN_TREND_POINTS = 2
"""A direction needs a start and an end."""

TREND_DEADBAND = 1.0
"""How far a score must move before it counts as a trend.

A dashboard that swings between "improving" and "declining" on rounding
teaches people to stop reading it.
"""


@dataclass(slots=True)
class ScoredResult:
    """The minimum a score needs to know about one result."""

    control_id: str
    status: ResultStatus
    severity: ControlSeverity
    framework_id: str | None = None
    target_id: str | None = None


@dataclass(slots=True)
class ScoreBreakdown:
    """A computed score and everything that went into it."""

    score: float
    grade: ScoreGrade
    weighted_score: float
    raw_pass_rate: float
    total: int
    passed: int
    failed: int
    warned: int
    excepted: int
    not_applicable: int
    not_assessed: int
    errored: int
    weight_total: float
    weight_earned: float
    by_severity: dict[str, dict[str, int]] = field(default_factory=dict)
    publishable: bool = True
    suppression_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form, suitable for the stored breakdown."""
        return {
            "score": round(self.score, 2),
            "grade": str(self.grade),
            "weighted_score": round(self.weighted_score, 2),
            "raw_pass_rate": round(self.raw_pass_rate, 2),
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "warned": self.warned,
            "excepted": self.excepted,
            "not_applicable": self.not_applicable,
            "not_assessed": self.not_assessed,
            "errored": self.errored,
            "weight_total": round(self.weight_total, 2),
            "weight_earned": round(self.weight_earned, 2),
            "by_severity": self.by_severity,
            "publishable": self.publishable,
            "suppression_reason": self.suppression_reason,
        }


def _tally_by_severity(results: list[ScoredResult]) -> dict[str, dict[str, int]]:
    """How each severity band fared, which is what a reader actually wants.

    An 87% that is entirely low-severity failures and an 87% that is
    three failing criticals are the same number and completely different
    situations.
    """
    tally: dict[str, dict[str, int]] = {}
    for result in results:
        band = tally.setdefault(
            str(result.severity), {"passed": 0, "failed": 0, "excepted": 0, "other": 0}
        )
        if result.status is ResultStatus.PASS:
            band["passed"] += 1
        elif result.status in (ResultStatus.FAIL, ResultStatus.WARNING):
            band["failed"] += 1
        elif result.status is ResultStatus.EXCEPTED:
            band["excepted"] += 1
        else:
            band["other"] += 1
    return tally


def compute_score(results: list[ScoredResult], *, minimum_controls: int = 1) -> ScoreBreakdown:
    """Score a set of results.

    **An excepted control counts as passing.** That is a real decision,
    not an oversight: an exception is a documented, approved, expiring
    acceptance of a specific risk, and treating it as a failure would
    mean an organization that governs its exceptions properly scores
    worse than one that never files any. The pressure that creates is
    exactly backwards. What stops this from becoming a loophole is that
    exceptions expire, are counted, and are reported separately -- so
    "our score is 94% and 40% of that is waivers" is a visible sentence.

    **The denominator excludes what was never assessed.** Scoring an
    unassessed control as a failure makes a partial run look like a
    catastrophe; scoring it as a pass makes it look like a success. Both
    are lies, and the honest answer is to score what was actually
    measured and report the coverage separately -- which
    :func:`coverage_of` does.

    ``minimum_controls`` suppresses publication of a score derived from
    too little. A framework with one assessed control out of three
    hundred can report 100%, and that number *will* be quoted.
    """
    scored = [one for one in results if one.status in SCORED_STATUSES]

    passed = sum(1 for one in scored if one.status is ResultStatus.PASS)
    failed = sum(1 for one in scored if one.status is ResultStatus.FAIL)
    warned = sum(1 for one in scored if one.status is ResultStatus.WARNING)
    excepted = sum(1 for one in scored if one.status is ResultStatus.EXCEPTED)
    not_applicable = sum(1 for one in results if one.status is ResultStatus.NOT_APPLICABLE)
    not_assessed = sum(1 for one in results if one.status is ResultStatus.NOT_ASSESSED)
    errored = sum(1 for one in results if one.status is ResultStatus.ERROR)

    total = len(scored)
    satisfied = passed + excepted

    weight_total = 0.0
    weight_earned = 0.0
    for one in scored:
        weight = SEVERITY_WEIGHTS[one.severity]
        weight_total += weight
        if one.status in (ResultStatus.PASS, ResultStatus.EXCEPTED):
            weight_earned += weight

    raw_pass_rate = (satisfied / total * 100.0) if total else 0.0

    # When every scored control is informational, the total weight is
    # zero and the weighted score is undefined. Falling back to the raw
    # rate is the only honest answer -- dividing by zero would be a
    # crash, and reporting 0% would say "totally non-compliant" about an
    # estate whose only findings are advisory.
    weighted_score = (weight_earned / weight_total * 100.0) if weight_total > 0 else raw_pass_rate

    publishable = total >= minimum_controls
    suppression_reason = (
        None
        if publishable
        else (
            f"Only {total} control(s) were scored; at least {minimum_controls} are needed "
            "before a score means anything."
        )
    )

    return ScoreBreakdown(
        score=weighted_score,
        grade=grade_for(weighted_score),
        weighted_score=weighted_score,
        raw_pass_rate=raw_pass_rate,
        total=total,
        passed=passed,
        failed=failed,
        warned=warned,
        excepted=excepted,
        not_applicable=not_applicable,
        not_assessed=not_assessed,
        errored=errored,
        weight_total=weight_total,
        weight_earned=weight_earned,
        by_severity=_tally_by_severity(results),
        publishable=publishable,
        suppression_reason=suppression_reason,
    )


def coverage_of(results: list[ScoredResult]) -> float:
    """What fraction of in-scope controls were actually measured, 0-100.

    The number that has to be printed next to every score. A 100% score
    across 4% coverage is not compliance, and reporting the two
    separately is what stops the first number from being read as though
    it were both.
    """
    applicable = [one for one in results if one.status is not ResultStatus.NOT_APPLICABLE]
    if not applicable:
        return 0.0
    measured = sum(
        1 for one in applicable if one.status not in (ResultStatus.NOT_ASSESSED, ResultStatus.ERROR)
    )
    return measured / len(applicable) * 100.0


def score_by_framework(
    results: list[ScoredResult], *, minimum_controls: int = 1
) -> dict[str, ScoreBreakdown]:
    """One score per framework."""
    grouped: dict[str, list[ScoredResult]] = {}
    for one in results:
        if one.framework_id is None:
            continue
        grouped.setdefault(one.framework_id, []).append(one)
    return {
        framework_id: compute_score(rows, minimum_controls=minimum_controls)
        for framework_id, rows in grouped.items()
    }


def score_by_target(
    results: list[ScoredResult], *, minimum_controls: int = 1
) -> dict[str, ScoreBreakdown]:
    """One score per asset, which is how remediation gets prioritised."""
    grouped: dict[str, list[ScoredResult]] = {}
    for one in results:
        if not one.target_id:
            continue
        grouped.setdefault(one.target_id, []).append(one)
    return {
        target_id: compute_score(rows, minimum_controls=minimum_controls)
        for target_id, rows in grouped.items()
    }


def combine_framework_scores(
    scores: dict[str, ScoreBreakdown], weights: dict[str, float] | None = None
) -> float:
    """Roll framework scores into one overall number.

    Weighted by each framework's configured weight, so an organization
    for which PCI-DSS is existential and CIS is advisory can say so.
    Unpublishable framework scores are excluded rather than counted as
    zero -- a framework with too little data must not drag the overall
    number down as though it had failed.
    """
    usable = {key: value for key, value in scores.items() if value.publishable}
    if not usable:
        return 0.0
    weights = weights or {}
    total_weight = sum(weights.get(key, 1.0) for key in usable)
    if total_weight <= 0:
        return 0.0
    return sum(value.score * weights.get(key, 1.0) for key, value in usable.items()) / total_weight


def delta_of(current: float, previous: float | None) -> float | None:
    """The movement between two scores, or ``None`` with no history."""
    return None if previous is None else round(current - previous, 2)


def trend_of(points: list[tuple[Any, float]]) -> str:
    """Whether a series of scores is improving, declining, or flat.

    Compares the first and last points with a one-point deadband, so
    ordinary noise does not get reported as a trend -- a dashboard that
    swings between "improving" and "declining" on rounding teaches
    people to stop reading it.
    """
    if len(points) < MIN_TREND_POINTS:
        return "insufficient_data"
    movement = points[-1][1] - points[0][1]
    if movement > TREND_DEADBAND:
        return "improving"
    if movement < -TREND_DEADBAND:
        return "declining"
    return "stable"


__all__ = [
    "MIN_TREND_POINTS",
    "TREND_DEADBAND",
    "ScoreBreakdown",
    "ScoredResult",
    "combine_framework_scores",
    "compute_score",
    "coverage_of",
    "delta_of",
    "score_by_framework",
    "score_by_target",
    "trend_of",
]
