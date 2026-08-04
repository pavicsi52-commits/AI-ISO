"""Scoring a change's risk from a likelihood/impact matrix and six independent dimensions.

Pure -- takes the inputs a risk assessment records, returns a score and
a banding. ``app/services/risk.py`` supplies the database and the clock
around this.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import (
    IMPACT_ORDER,
    LIKELIHOOD_ORDER,
    ChangeType,
    RiskImpact,
    RiskLevel,
    RiskLikelihood,
)

_MAX_LIKELIHOOD_ORDER = max(LIKELIHOOD_ORDER.values())
_MAX_IMPACT_ORDER = max(IMPACT_ORDER.values())


@dataclass(frozen=True, slots=True)
class RiskDimensions:
    """The six independent risk readings docs/053 names.

    Each is scored on the same published :class:`RiskImpact` scale
    deliberately, so no single dimension can be quietly averaged away by
    the others -- a change that is a severe security risk and a minimal
    everything-else risk is still a severe risk.
    """

    technical: RiskImpact
    business: RiskImpact
    operational: RiskImpact
    security: RiskImpact
    compliance: RiskImpact
    dependency: RiskImpact

    def worst(self) -> RiskImpact:
        """The single worst-scored dimension."""
        return max(
            (
                self.technical,
                self.business,
                self.operational,
                self.security,
                self.compliance,
                self.dependency,
            ),
            key=lambda one: IMPACT_ORDER[one],
        )


def matrix_score(likelihood: RiskLikelihood, impact: RiskImpact) -> float:
    """The classic likelihood x impact score, normalised to ``0.0``-``1.0``."""
    return (LIKELIHOOD_ORDER[likelihood] * IMPACT_ORDER[impact]) / (
        _MAX_LIKELIHOOD_ORDER * _MAX_IMPACT_ORDER
    )


def dimension_score(dimensions: RiskDimensions) -> float:
    """The worst of the six independent dimensions, normalised to ``0.0``-``1.0``.

    The worst reading, not their average: nine dimensions at MINIMAL and
    one at SEVERE is still a severe risk, the same reasoning Prompt 052
    applies to an incident's overall impact.
    """
    return IMPACT_ORDER[dimensions.worst()] / _MAX_IMPACT_ORDER


def automated_score(
    *, likelihood: RiskLikelihood, impact: RiskImpact, dimensions: RiskDimensions
) -> float:
    """The composite automated risk score, ``0.0``-``1.0``.

    The higher of the matrix score and the worst dimension score --
    whichever paints the darker picture wins, rather than one
    diluting the other.
    """
    return max(matrix_score(likelihood, impact), dimension_score(dimensions))


_RISK_LEVEL_THRESHOLDS: tuple[tuple[float, RiskLevel], ...] = (
    (0.75, RiskLevel.CRITICAL),
    (0.50, RiskLevel.HIGH),
    (0.25, RiskLevel.MEDIUM),
)


def risk_level_for(score: float) -> RiskLevel:
    """Band a ``0.0``-``1.0`` automated score into a :class:`RiskLevel`."""
    for threshold, level in _RISK_LEVEL_THRESHOLDS:
        if score >= threshold:
            return level
    return RiskLevel.LOW


def effective_risk_level(*, automated: RiskLevel, override: RiskLevel | None) -> RiskLevel:
    """The risk level that actually governs a change: an override if one was recorded.

    A human may override the computed banding, but the override is
    always the *effective* value read everywhere else in this
    service -- CAB eligibility, approval policy, conflict-detection
    weighting. The automated score is never silently reinstated once a
    reviewer has looked at it and disagreed.
    """
    return override if override is not None else automated


def approval_recommendation_for(risk_level: RiskLevel, change_type: ChangeType) -> str:
    """A human-readable recommendation for what a risk level implies for approval."""
    if change_type is ChangeType.STANDARD:
        return "Standard change: pre-approved template, no additional approval required."
    if change_type is ChangeType.EMERGENCY:
        return "Emergency change: implement now, secure approval as soon as practicable."
    if risk_level is RiskLevel.CRITICAL:
        return "Critical risk: full CAB review required, minimum two independent approvers."
    if risk_level is RiskLevel.HIGH:
        return "High risk: CAB review required."
    if risk_level is RiskLevel.MEDIUM:
        return "Medium risk: standard approval chain, CAB review not required."
    return "Low risk: expedited approval eligible."


__all__ = [
    "RiskDimensions",
    "approval_recommendation_for",
    "automated_score",
    "dimension_score",
    "effective_risk_level",
    "matrix_score",
    "risk_level_for",
]
