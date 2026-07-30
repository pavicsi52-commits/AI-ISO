"""``policy_approvals``, ``policy_quotas``, and ``policy_simulations``.

The three things a decision can produce besides an answer: an obligation
someone must satisfy, a budget it consumed, and a rehearsal of what
would have happened.
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
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import (
    ActionType,
    ApprovalStatus,
    ApprovalType,
    JobStatus,
    QuotaPeriod,
    QuotaScope,
    ResourceType,
    SimulationKind,
    SubjectType,
)


class PolicyApproval(BaseModel):
    """``policy_approvals`` -- one outstanding obligation and its outcome."""

    __tablename__ = "policy_approvals"
    __table_args__ = (
        Index("ix_policy_approval_pending", "organization_id", "status", "expires_at"),
    )

    policy_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    decision_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)

    approval_type: Mapped[ApprovalType] = mapped_column(
        String(32), default=ApprovalType.SINGLE, index=True
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        String(16), default=ApprovalStatus.PENDING, index=True
    )

    subject_type: Mapped[SubjectType] = mapped_column(String(32), default=SubjectType.USER)
    subject_id: Mapped[str] = mapped_column(String(255), index=True)
    resource_type: Mapped[ResourceType] = mapped_column(
        String(64), default=ResourceType.CUSTOM_RESOURCE
    )
    resource_id: Mapped[str | None] = mapped_column(String(255), default=None)
    action: Mapped[ActionType] = mapped_column(String(32), default=ActionType.EXECUTE)

    required_levels: Mapped[int] = mapped_column(Integer, default=1)
    """How many distinct approvals are needed ("Multi-Level Approval")."""

    required_roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    decisions: Mapped[list[Any]] = mapped_column(JSON, default=list)
    """Each approver's answer, appended.

    A list rather than a count, because "who approved this" is the
    question an audit asks and a counter cannot answer. Also what makes
    the one-approver-cannot-count-twice rule enforceable.
    """

    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    reason: Mapped[str | None] = mapped_column(Text, default=None)
    is_emergency: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    """Break-glass.

    Always audited and always notified -- that is what makes it
    acceptable to have at all, and why it is a flag on the row rather
    than an ordinary approval nobody can distinguish afterwards.
    """

    context_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PolicyQuota(BaseModel):
    """``policy_quotas`` -- a consumption budget and its current usage.

    Usage lives on the row rather than being recomputed, which is the
    opposite of how this platform treats statistics elsewhere and is
    correct here: a quota is *enforced* on the request path, so counting
    the underlying events on every check would make the cost of the
    check grow with how much the tenant has used.

    The consequence is that consumption must be incremented atomically
    in the database, never read-modify-written in Python -- see the
    repository.
    """

    __tablename__ = "policy_quotas"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "scope", "scope_id", "resource", name="uq_policy_quota"
        ),
        Index("ix_policy_quota_period", "organization_id", "period_started_at"),
    )

    policy_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)

    scope: Mapped[QuotaScope] = mapped_column(
        String(32), default=QuotaScope.ORGANIZATION, index=True
    )
    scope_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    """Which organization/project/user this budget belongs to.

    Empty string rather than NULL: it is part of the uniqueness
    constraint, and PostgreSQL treats NULLs as distinct, so a nullable
    column would let unlimited duplicate organization-wide quotas exist
    for the same resource.
    """

    resource: Mapped[str] = mapped_column(String(128), default="requests", index=True)
    limit_value: Mapped[float] = mapped_column(Float, default=0.0)
    consumed: Mapped[float] = mapped_column(Float, default=0.0)
    period: Mapped[QuotaPeriod] = mapped_column(String(16), default=QuotaPeriod.MONTHLY)
    period_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    is_hard_limit: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    """Whether exceeding refuses or merely warns.

    A soft quota is genuinely useful -- it is how a limit gets
    introduced without breaking the people already over it -- but the
    default is hard, because a limit nobody enforces is a number in a
    table.
    """

    warning_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    exceeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    exceeded_count: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text, default=None)


class PolicySimulation(BaseModel):
    """``policy_simulations`` -- a rehearsal and what it found."""

    __tablename__ = "policy_simulations"
    __table_args__ = (Index("ix_policy_simulation_org", "organization_id", "started_at"),)

    label: Mapped[str] = mapped_column(String(255))
    kind: Mapped[SimulationKind] = mapped_column(
        String(32), default=SimulationKind.WHAT_IF, index=True
    )
    status: Mapped[JobStatus] = mapped_column(String(16), default=JobStatus.PENDING, index=True)

    draft_policy_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    """Unpublished policies to include as if they were live.

    The whole point of a preview: answering "what would happen if I
    published this" without publishing it.
    """

    request_count: Mapped[int] = mapped_column(Integer, default=0)
    allowed_count: Mapped[int] = mapped_column(Integer, default=0)
    denied_count: Mapped[int] = mapped_column(Integer, default=0)
    changed_count: Mapped[int] = mapped_column(Integer, default=0)
    """How many outcomes differ from what the live catalogue gives.

    The number the whole feature exists to produce. A simulation that
    reports only totals tells you what the new rules do; this tells you
    what they *break*.
    """

    conflicts: Mapped[list[Any]] = mapped_column(JSON, default=list)
    results: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    summary: Mapped[str | None] = mapped_column(Text, default=None)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["PolicyApproval", "PolicyQuota", "PolicySimulation"]
