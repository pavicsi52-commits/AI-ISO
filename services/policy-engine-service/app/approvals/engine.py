"""Approval arithmetic: who has answered, and whether that is enough.

Pure functions over an approval's recorded decisions. The storage side
lives in the service; this decides what a set of answers *means*.

**One rejection ends it.** An approval requiring three sign-offs and
receiving two approvals and one rejection is rejected, not pending --
waiting for a third opinion after someone has objected turns a veto into
a vote, which is not what an approval gate is.

**An approver cannot count twice.** Multi-level approval exists so that
several people look at something; letting one person satisfy every level
by answering repeatedly makes the requirement decorative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.models.enums import ApprovalStatus, ApprovalType


@dataclass(frozen=True, slots=True)
class ApproverDecision:
    """One person's answer."""

    approver_id: str
    approved: bool
    decided_at: datetime
    comment: str = ""
    roles: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form."""
        return {
            "approver_id": self.approver_id,
            "approved": self.approved,
            "decided_at": self.decided_at.isoformat(),
            "comment": self.comment,
            "roles": list(self.roles),
        }


@dataclass(slots=True)
class ApprovalState:
    """Where an approval stands, and why."""

    status: ApprovalStatus
    reason: str
    approvals: int = 0
    rejections: int = 0
    remaining: int = 0
    decisions: list[ApproverDecision] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form."""
        return {
            "status": str(self.status),
            "reason": self.reason,
            "approvals": self.approvals,
            "rejections": self.rejections,
            "remaining": self.remaining,
            "decisions": [one.as_dict() for one in self.decisions],
        }


def decision_from_dict(payload: dict[str, Any]) -> ApproverDecision:
    """Rebuild one recorded answer from stored JSON."""
    decided = payload.get("decided_at")
    moment = (
        datetime.fromisoformat(str(decided).replace("Z", "+00:00"))
        if decided
        else datetime.now(UTC)
    )
    return ApproverDecision(
        approver_id=str(payload.get("approver_id") or ""),
        approved=bool(payload.get("approved", False)),
        decided_at=moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC),
        comment=str(payload.get("comment") or ""),
        roles=tuple(str(one) for one in payload.get("roles") or ()),
    )


def required_levels(
    approval_type: ApprovalType, *, declared: int = 1, risk_score: float = 0.0
) -> int:
    """How many distinct approvals a request needs.

    ``RISK_BASED`` is the only type that computes rather than reads: it
    scales with the decision's risk, so a routine change needs one
    sign-off and a dangerous one needs three, without an author having
    to enumerate the bands.
    """
    fixed = _FIXED_LEVELS.get(approval_type)
    if fixed is not None:
        return fixed
    if approval_type is ApprovalType.RISK_BASED:
        return _risk_based_levels(risk_score)
    if approval_type is ApprovalType.MULTI_LEVEL:
        # A declared "multi-level, one approver" is a contradiction; the
        # floor is what makes the type mean anything.
        return max(2, declared)
    return max(1, declared)


_FIXED_LEVELS: dict[ApprovalType, int] = {
    ApprovalType.AUTOMATIC: 0,
    # Break-glass is one self-approval by design. What makes it
    # acceptable is not scarcity of approvers but that it is flagged,
    # audited, and notified every single time.
    ApprovalType.EMERGENCY: 1,
}
"""Types whose level count does not depend on anything."""


def _risk_based_levels(risk_score: float) -> int:
    """Sign-offs required for a risk-scaled approval."""
    high, medium = 0.8, 0.5
    if risk_score >= high:
        return 3
    if risk_score >= medium:
        return 2
    return 1


def validate_approver(
    approver_id: str,
    *,
    decisions: list[ApproverDecision],
    required_roles: list[str],
    approver_roles: list[str],
    requested_by: UUID | str | None,
    allow_self_approval: bool,
) -> None:
    """Check one person may answer this approval.

    Raises:
        ValidationError: If they have already answered, lack a required
            role, or are the requester and self-approval is not allowed.
    """
    if any(one.approver_id == approver_id for one in decisions):
        raise ValidationError(
            f"Approver {approver_id!r} has already recorded a decision on this request. "
            "Multi-level approval requires distinct approvers."
        )
    if required_roles and not set(required_roles) & set(approver_roles):
        raise ValidationError(
            f"This approval requires one of these roles: {', '.join(sorted(required_roles))}."
        )
    if not allow_self_approval and requested_by is not None and str(requested_by) == approver_id:
        raise ValidationError(
            "The person who requested this approval cannot also grant it. "
            "Use an emergency approval if there is genuinely nobody else."
        )


def resolve(
    decisions: list[ApproverDecision],
    *,
    required: int,
    expires_at: datetime,
    now: datetime | None = None,
) -> ApprovalState:
    """Work out where an approval stands.

    Order matters: **rejection first, then expiry, then sufficiency.**
    A request that was rejected and has since expired is rejected -- the
    objection is the fact worth recording, and reporting it as "expired"
    would lose why nobody acted on it.
    """
    moment = now or datetime.now(UTC)
    approvals = [one for one in decisions if one.approved]
    rejections = [one for one in decisions if not one.approved]

    if rejections:
        who = rejections[0]
        return ApprovalState(
            status=ApprovalStatus.REJECTED,
            reason=(
                f"Rejected by {who.approver_id!r}" + (f": {who.comment}" if who.comment else ".")
            ),
            approvals=len(approvals),
            rejections=len(rejections),
            remaining=0,
            decisions=decisions,
        )

    if len(approvals) >= required:
        return ApprovalState(
            status=ApprovalStatus.APPROVED,
            reason=f"{len(approvals)} of {required} required approvals recorded.",
            approvals=len(approvals),
            rejections=0,
            remaining=0,
            decisions=decisions,
        )

    if moment >= expires_at:
        # Checked after sufficiency, so an approval that got its last
        # sign-off a second before the deadline is approved rather than
        # lost to a clock.
        return ApprovalState(
            status=ApprovalStatus.EXPIRED,
            reason=(
                f"Expired at {expires_at.isoformat()} with {len(approvals)} of "
                f"{required} required approvals."
            ),
            approvals=len(approvals),
            rejections=0,
            remaining=required - len(approvals),
            decisions=decisions,
        )

    return ApprovalState(
        status=ApprovalStatus.PENDING,
        reason=f"Awaiting {required - len(approvals)} more approval(s).",
        approvals=len(approvals),
        rejections=0,
        remaining=required - len(approvals),
        decisions=decisions,
    )


def expiry_for(approval_type: ApprovalType, *, hours: int, now: datetime | None = None) -> datetime:
    """When an approval of this type stops being actionable.

    Emergency approvals expire fast -- an hour, not two days. Break-glass
    that stays open overnight is a standing grant nobody remembers
    issuing, which is the exact thing the flag exists to prevent.
    """
    moment = now or datetime.now(UTC)
    if approval_type is ApprovalType.EMERGENCY:
        return moment + timedelta(hours=1)
    return moment + timedelta(hours=hours)


__all__ = [
    "ApprovalState",
    "ApproverDecision",
    "decision_from_dict",
    "expiry_for",
    "required_levels",
    "resolve",
    "validate_approver",
]
