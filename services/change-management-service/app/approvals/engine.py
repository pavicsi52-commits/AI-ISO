"""Evaluating a multi-level approval chain.

Pure -- takes the steps recorded so far, answers whether the chain as a
whole has resolved and, if not, which level is still active.
``app/services/approval.py`` supplies the database and the clock around
these decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.models.enums import ApprovalPolicy, ApprovalStatus, RiskLevel

_RESOLVED_APPROVED: frozenset[ApprovalStatus] = frozenset(
    {ApprovalStatus.APPROVED, ApprovalStatus.CONDITIONAL}
)


@dataclass(frozen=True, slots=True)
class ApprovalStep:
    """One approver's step in a chain, as the engine needs it."""

    level: int
    approver_id: str
    status: ApprovalStatus


def levels_of(steps: list[ApprovalStep]) -> list[int]:
    """Every distinct level present, ascending."""
    return sorted({one.level for one in steps})


def steps_at_level(steps: list[ApprovalStep], level: int) -> list[ApprovalStep]:
    """The steps belonging to one level."""
    return [one for one in steps if one.level == level]


def level_status(steps: list[ApprovalStep]) -> ApprovalStatus:
    """One level's own outcome, from the steps that belong to it.

    A single rejection fails the whole level regardless of how many
    other approvers said yes -- a level exists so that *every* required
    approver at it agrees, not a majority of them. A level with no steps
    at all is, definitionally, pending: there is nothing for it to have
    resolved from.

    A ``DELEGATED`` step is excluded from "every step must agree": it
    was closed out precisely because a fresh step at the same level now
    carries its resolution (see ``ApprovalService.delegate``), and
    counting the closed-out original against the level forever would
    mean a delegated level could never resolve, no matter what its
    delegate went on to decide.
    """
    if not steps:
        return ApprovalStatus.PENDING
    active = [one for one in steps if one.status is not ApprovalStatus.DELEGATED]
    if not active:
        return ApprovalStatus.PENDING
    if any(one.status is ApprovalStatus.REJECTED for one in active):
        return ApprovalStatus.REJECTED
    if all(one.status in _RESOLVED_APPROVED for one in active):
        if any(one.status is ApprovalStatus.CONDITIONAL for one in active):
            return ApprovalStatus.CONDITIONAL
        return ApprovalStatus.APPROVED
    return ApprovalStatus.PENDING


def active_level(steps: list[ApprovalStep]) -> int | None:
    """The lowest level not yet resolved, or ``None`` if every level has resolved.

    Levels gate sequentially: a level 2 approver's decision is
    irrelevant while level 1 has not yet resolved, so this is also the
    level a caller should actually be asking anyone to act on right now.
    """
    for level in levels_of(steps):
        if level_status(steps_at_level(steps, level)) is ApprovalStatus.PENDING:
            return level
    return None


def chain_status(steps: list[ApprovalStep]) -> ApprovalStatus:
    """The whole chain's outcome.

    Processes levels in order and stops at the first one that is not a
    clean ``APPROVED`` -- a rejection or a still-pending level below the
    top makes the chain's overall status that level's status, regardless
    of what a higher level's steps (which should not exist yet in a
    correctly-driven chain) might say.
    """
    if not steps:
        return ApprovalStatus.PENDING
    outcome = ApprovalStatus.APPROVED
    for level in levels_of(steps):
        status = level_status(steps_at_level(steps, level))
        if status in (ApprovalStatus.PENDING, ApprovalStatus.REJECTED):
            return status
        if status is ApprovalStatus.CONDITIONAL:
            outcome = ApprovalStatus.CONDITIONAL
    return outcome


def is_expired(expires_at: datetime | None, *, now: datetime) -> bool:
    """Whether an approval step's own expiry has passed."""
    return expires_at is not None and now >= expires_at


def required_levels_for(
    *, policy: ApprovalPolicy, risk_level: RiskLevel | None, minimum_approvals_high_risk: int
) -> int:
    """How many approval levels a chain needs, before any steps exist yet.

    ``SINGLE`` is always one level. ``RISK_BASED`` scales with severity,
    using the organization's own configured floor for high-and-critical
    risk rather than a number buried in code. ``MULTI_LEVEL`` and
    ``ROLE_BASED`` both default to two -- a requester approving their own
    change is not independent review, so the platform default is never
    one level for either.
    """
    if policy is ApprovalPolicy.SINGLE:
        return 1
    if policy is ApprovalPolicy.RISK_BASED:
        if risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) or risk_level is None:
            return max(minimum_approvals_high_risk, 1)
        return 1
    return 2


__all__ = [
    "ApprovalStep",
    "active_level",
    "chain_status",
    "is_expired",
    "level_status",
    "levels_of",
    "required_levels_for",
    "steps_at_level",
]
