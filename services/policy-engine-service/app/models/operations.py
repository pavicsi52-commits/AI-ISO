"""``policy_statistics``, ``policy_reports``, and ``policy_audit``.

The operational surface: what the estate looks like in aggregate, what
was reported, and what was done.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuditAction, AuditOutcome, JobStatus, ReportKind


class PolicyStatistics(BaseModel):
    """``policy_statistics`` -- one rollup row per organization.

    Updated in place rather than appended. The underlying decisions and
    violations are the history; a second time series of the same numbers
    would only be another thing to keep consistent with them.
    """

    __tablename__ = "policy_statistics"
    __table_args__ = (UniqueConstraint("organization_id", name="uq_policy_statistics_org"),)

    policy_count: Mapped[int] = mapped_column(Integer, default=0)
    published_count: Mapped[int] = mapped_column(Integer, default=0)
    draft_count: Mapped[int] = mapped_column(Integer, default=0)

    decision_count: Mapped[int] = mapped_column(Integer, default=0)
    allowed_count: Mapped[int] = mapped_column(Integer, default=0)
    denied_count: Mapped[int] = mapped_column(Integer, default=0)
    approval_required_count: Mapped[int] = mapped_column(Integer, default=0)

    violation_count: Mapped[int] = mapped_column(Integer, default=0)
    open_violation_count: Mapped[int] = mapped_column(Integer, default=0)
    quota_violation_count: Mapped[int] = mapped_column(Integer, default=0)

    pending_approval_count: Mapped[int] = mapped_column(Integer, default=0)
    expired_approval_count: Mapped[int] = mapped_column(Integer, default=0)

    average_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    p95_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    """Reported alongside the mean, not instead of it.

    A mean decision latency is dominated by the fast majority and hides
    the tail entirely -- and the tail is what a caller with a request
    timeout actually experiences.
    """

    unused_policy_count: Mapped[int] = mapped_column(Integer, default=0)
    """Published policies nothing has matched.

    Either dead weight or -- more dangerous -- a rule whose conditions
    have drifted out of line with reality, so it looks like governance
    and enforces nothing.
    """

    policy_usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    decisions_by_effect: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    decisions_by_category: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PolicyReport(BaseModel):
    """``policy_reports`` -- one generated report and its payload."""

    __tablename__ = "policy_reports"
    __table_args__ = (Index("ix_policy_report_org", "organization_id", "generated_at"),)

    title: Mapped[str] = mapped_column(String(255))
    kind: Mapped[ReportKind] = mapped_column(String(32), default=ReportKind.POLICY, index=True)
    status: Mapped[JobStatus] = mapped_column(String(16), default=JobStatus.PENDING, index=True)

    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    payload: Mapped[bytes | None] = mapped_column(LargeBinary, default=None)
    content_type: Mapped[str] = mapped_column(String(128), default="application/json")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), default=None)

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    error: Mapped[str | None] = mapped_column(Text, default=None)


class PolicyAudit(BaseModel):
    """``policy_audit`` -- the immutable trail (docs/050 "AUDIT").

    Append-only by construction: nothing in this service updates a row
    here. For the service that authorizes every protected operation on
    the platform, a mutable audit trail would be worth less than no
    trail at all -- it would look authoritative while being editable by
    whoever the trail is about.
    """

    __tablename__ = "policy_audit"
    __table_args__ = (
        Index("ix_policy_audit_org", "organization_id", "occurred_at"),
        Index("ix_policy_audit_entity", "entity_type", "entity_id"),
    )

    action: Mapped[AuditAction] = mapped_column(
        String(32), default=AuditAction.ADMINISTRATIVE, index=True
    )
    outcome: Mapped[AuditOutcome] = mapped_column(
        String(16), default=AuditOutcome.SUCCESS, index=True
    )

    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)

    reason: Mapped[str | None] = mapped_column(Text, default=None)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["PolicyAudit", "PolicyReport", "PolicyStatistics"]
