"""Risk classification (docs/060 "GUARDRAILS": Risk Classification).

A genuine gap: nothing else in this platform scores risk *per request*.
``policy-engine-service``'s own ``risk_weight`` is a static value
configured once on a policy, not something computed from the shape of
one actual tool call or model turn. This module is that missing live
classifier -- pure and deterministic, so the same inputs always score
the same, and cheap enough to run on every guarded action.

The score is a simple weighted sum, not a model -- explainable by
construction, since :attr:`RiskAssessment.reasons` names exactly which
signals fired. That is the point: an agent's own audit trail must be
able to say *why* an action was flagged, not just that it was.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.enums import PermissionCategory, RiskLevel

_CATEGORY_WEIGHT: dict[PermissionCategory, int] = {
    PermissionCategory.ADMINISTRATIVE: 4,
    PermissionCategory.DELEGATION: 3,
    PermissionCategory.FILESYSTEM: 3,
    PermissionCategory.NETWORK: 2,
    PermissionCategory.DATA_ACCESS: 2,
    PermissionCategory.MODEL_ACCESS: 1,
    PermissionCategory.MEMORY_ACCESS: 1,
    PermissionCategory.TOOL_INVOCATION: 1,
}
"""How risky each permission category is on its own, before any of the
per-request signals below are added on top."""

_LEVEL_THRESHOLDS: tuple[tuple[int, RiskLevel], ...] = (
    (9, RiskLevel.CRITICAL),
    (6, RiskLevel.HIGH),
    (3, RiskLevel.MEDIUM),
)
"""Checked highest-first; a score below every threshold is
:class:`RiskLevel.LOW`."""


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    """One request's own computed risk."""

    level: RiskLevel
    score: int
    reasons: tuple[str, ...]

    @property
    def requires_review(self) -> bool:
        """Whether this assessment is severe enough to hold for human
        approval rather than letting it proceed automatically."""
        return self.level in (RiskLevel.HIGH, RiskLevel.CRITICAL)


def classify_risk(
    *,
    category: PermissionCategory | None = None,
    is_mutating: bool = False,
    injection_findings: tuple[str, ...] = (),
    redaction_findings: tuple[str, ...] = (),
    is_first_use: bool = False,
) -> RiskAssessment:
    """Score one guarded action from whatever signals the caller already
    has in hand -- the permission category a tool call falls under, an
    already-run guardrail's own findings, and whether this is a tool an
    agent has never invoked before.

    Every signal is optional: a caller screening plain text (no tool,
    no category) still gets a meaningful score from injection/redaction
    findings alone.
    """
    score = 0
    reasons: list[str] = []

    if category is not None:
        score += _CATEGORY_WEIGHT.get(category, 1)
        reasons.append(f"category:{category!s}")

    if is_mutating:
        score += 3
        reasons.append("mutating_action")

    if injection_findings:
        score += 4
        reasons.append("prompt_injection_detected")

    if redaction_findings:
        score += 2
        reasons.append("secret_or_pii_present")

    if is_first_use:
        score += 1
        reasons.append("first_use_of_tool")

    level = RiskLevel.LOW
    for threshold, candidate in _LEVEL_THRESHOLDS:
        if score >= threshold:
            level = candidate
            break

    return RiskAssessment(level=level, score=score, reasons=tuple(reasons))


__all__ = ["RiskAssessment", "classify_risk"]
