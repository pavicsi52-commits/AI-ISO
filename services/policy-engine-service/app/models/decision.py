"""``policy_decisions``, ``policy_violations``, and ``policy_exceptions``.

What the engine decided, what broke a rule, and what was excused.

**A decision row is evidence, not a cache entry.** It records the effect,
the policies that produced it, and the full evaluation trace, because
the question asked afterwards is never "what did it decide" -- that was
obvious at the time -- but "why", months later, to somebody who was not
there.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import (
    ActionType,
    ComplianceStandard,
    PolicyEffect,
    ResourceType,
    SubjectType,
    ViolationStatus,
)


class PolicyDecision(BaseModel):
    """``policy_decisions`` -- one authorization answer, with its reasoning."""

    __tablename__ = "policy_decisions"
    __table_args__ = (
        Index("ix_policy_decision_lookup", "organization_id", "decided_at"),
        Index("ix_policy_decision_subject", "organization_id", "subject_id"),
        Index("ix_policy_decision_effect", "organization_id", "effect", "decided_at"),
    )

    request_id: Mapped[str | None] = mapped_column(String(64), default=None, index=True)
    """The caller's correlation id.

    How a denial reported by a user in one service is tied back to the
    decision that produced it -- without it, "I got a 403" is
    unanswerable across service boundaries.
    """

    subject_type: Mapped[SubjectType] = mapped_column(
        String(32), default=SubjectType.USER, index=True
    )
    subject_id: Mapped[str] = mapped_column(String(255), index=True)
    resource_type: Mapped[ResourceType] = mapped_column(
        String(64), default=ResourceType.CUSTOM_RESOURCE, index=True
    )
    resource_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    action: Mapped[ActionType] = mapped_column(String(32), default=ActionType.READ, index=True)

    effect: Mapped[PolicyEffect] = mapped_column(String(32), default=PolicyEffect.DENY, index=True)
    permitted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    """Whether the caller may proceed *now*.

    Separate from ``effect`` because REQUIRE_APPROVAL is neither an
    allow nor a deny, and a dashboard counting "allowed vs denied" needs
    a straight answer that does not quietly file obligations under
    permitted. Derived from PERMITTING_EFFECTS, never set by hand.
    """

    reason: Mapped[str] = mapped_column(Text, default="")
    matched_policy_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    deciding_policy_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    """The single policy whose effect won.

    Stored alongside the full matched list because "which one denied me"
    is the first question and reconstructing it from a list plus the
    precedence table is work nobody should have to do twice.
    """

    evaluation_trace: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    required_approvals: Mapped[list[Any]] = mapped_column(JSON, default=list)
    obligations: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)

    context_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    """The attributes the decision saw, sensitive ones redacted.

    Without it a trace is unreadable a week later: the conditions are
    there but the values that made them true are gone, so nobody can
    tell whether the policy was wrong or the input was.
    """

    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    policies_considered: Mapped[int] = mapped_column(Integer, default=0)
    cached: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    simulated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    """Whether this came from a simulation rather than a live request.

    Indexed and filtered out of every operational statistic. A
    simulation runs the real engine, so its decisions are
    indistinguishable from live ones without this flag -- and a
    what-if analysis silently inflating the denial rate would make the
    metric useless exactly when someone is using it to plan a change.
    """

    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    error: Mapped[str | None] = mapped_column(Text, default=None)


class PolicyViolation(BaseModel):
    """``policy_violations`` -- a rule broken, kept as evidence."""

    __tablename__ = "policy_violations"
    __table_args__ = (
        Index("ix_policy_violation_open", "organization_id", "status", "detected_at"),
    )

    policy_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    decision_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)

    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    standard: Mapped[ComplianceStandard] = mapped_column(
        String(32), default=ComplianceStandard.SECURITY, index=True
    )
    severity: Mapped[str] = mapped_column(String(16), default="medium", index=True)

    subject_type: Mapped[SubjectType] = mapped_column(String(32), default=SubjectType.USER)
    subject_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    resource_type: Mapped[ResourceType] = mapped_column(
        String(64), default=ResourceType.CUSTOM_RESOURCE
    )
    resource_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)

    status: Mapped[ViolationStatus] = mapped_column(
        String(16), default=ViolationStatus.OPEN, index=True
    )
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    resolution_note: Mapped[str | None] = mapped_column(Text, default=None)


class PolicyException(BaseModel):
    """``policy_exceptions`` -- a scoped, expiring waiver of one policy.

    **Every exception expires.** ``expires_at`` is not nullable, and that
    is the whole design: a permanent exception is not an exception, it is
    an undocumented policy change that no review will ever surface
    because it does not look like one.
    """

    __tablename__ = "policy_exceptions"
    __table_args__ = (
        Index("ix_policy_exception_active", "organization_id", "policy_id", "expires_at"),
    )

    policy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("policies.id", ondelete="CASCADE"), index=True
    )

    reason: Mapped[str] = mapped_column(Text)
    """Never optional. An exception without a stated reason is
    indistinguishable from a mistake when somebody reviews it later."""

    subject_type: Mapped[SubjectType | None] = mapped_column(String(32), default=None)
    subject_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    resource_type: Mapped[ResourceType | None] = mapped_column(String(64), default=None)
    resource_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)

    granted_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(default=None)

    use_count: Mapped[int] = mapped_column(Integer, default=0)
    """How often it has been relied on.

    A waiver used a thousand times is not an exception; it is the real
    policy, and the number is what makes that visible.
    """


__all__ = ["PolicyDecision", "PolicyException", "PolicyViolation"]
