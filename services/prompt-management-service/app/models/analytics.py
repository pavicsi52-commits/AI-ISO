"""``prompt_optimizations``, ``prompt_statistics``, ``prompt_reports``,
and ``prompt_audit``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

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
    AuditAction,
    OptimizationKind,
    OptimizationStatus,
    ReportFormat,
    ReportKind,
    ReportStatus,
)


class PromptOptimization(BaseModel):
    """``prompt_optimizations`` -- one suggested improvement to a revision.

    **A suggestion is never applied automatically.** A prompt's exact
    wording is the thing under version control and approval here, so
    rewriting it without a human accepting the change would bypass the
    entire governance workflow this service exists to enforce. Accepting
    one creates a new draft version through the normal path.
    """

    __tablename__ = "prompt_optimizations"
    __table_args__ = (
        Index("ix_prompt_optimization_kind", "kind"),
        Index("ix_prompt_optimization_status", "status"),
    )

    prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[OptimizationKind] = mapped_column(String(32), index=True)
    status: Mapped[OptimizationStatus] = mapped_column(
        String(16), default=OptimizationStatus.SUGGESTED, index=True
    )
    rationale: Mapped[str] = mapped_column(Text)
    suggested_body: Mapped[str | None] = mapped_column(Text, default=None)
    original_tokens: Mapped[int] = mapped_column(Integer, default=0)
    optimized_tokens: Mapped[int] = mapped_column(Integer, default=0)
    token_saving: Mapped[int] = mapped_column(Integer, default=0)
    saving_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_cost_saving_usd: Mapped[float] = mapped_column(Float, default=0.0)
    suggested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    decided_by: Mapped[str | None] = mapped_column(String(128), default=None)
    resulting_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="SET NULL"), default=None
    )
    """The draft revision created when this suggestion was accepted --
    the audit link between "we suggested this" and "this is what
    shipped"."""


class PromptStatistic(BaseModel):
    """``prompt_statistics`` -- one rolled-up activity window, org-wide."""

    __tablename__ = "prompt_statistics"
    __table_args__ = (Index("ix_prompt_statistics_window_start", "window_start"),)

    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    total_prompts: Mapped[int] = mapped_column(Integer, default=0)
    published_prompts: Mapped[int] = mapped_column(Integer, default=0)
    execution_count: Mapped[int] = mapped_column(Integer, default=0)
    executions_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    executions_failed: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    average_latency_ms: Mapped[float | None] = mapped_column(Float, default=None)
    average_cost_usd: Mapped[float | None] = mapped_column(Float, default=None)
    optimization_token_savings: Mapped[int] = mapped_column(Integer, default=0)
    """ "ANALYTICS": Optimization Savings -- summed from accepted
    optimizations only, never from suggestions nobody took."""
    security_findings: Mapped[int] = mapped_column(Integer, default=0)
    by_prompt_type: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    by_category: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    top_prompts: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)


class PromptReport(BaseModel):
    """``prompt_reports`` -- one generated report."""

    __tablename__ = "prompt_reports"
    __table_args__ = (Index("ix_prompt_reports_kind", "kind"),)

    kind: Mapped[ReportKind] = mapped_column(String(16), index=True)
    report_format: Mapped[ReportFormat] = mapped_column(String(16), default=ReportFormat.JSON)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[ReportStatus] = mapped_column(String(16), default=ReportStatus.PENDING)
    content: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    row_count: Mapped[int | None] = mapped_column(Integer, default=None)
    generated_by: Mapped[str | None] = mapped_column(String(128), default=None)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    duration_ms: Mapped[float | None] = mapped_column(Float, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)


class PromptAudit(BaseModel):
    """``prompt_audit`` -- the append-only audit trail.

    docs/061 requires an *immutable* audit history. Nothing in this
    service ever updates or deletes one of these rows; the repository
    exposes create and read only.
    """

    __tablename__ = "prompt_audit"
    __table_args__ = (
        Index("ix_prompt_audit_action", "action"),
        Index("ix_prompt_audit_entity_id", "entity_id"),
        Index("ix_prompt_audit_occurred_at", "occurred_at"),
    )

    action: Mapped[AuditAction] = mapped_column(String(32), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    entity_reference: Mapped[str | None] = mapped_column(String(255), default=None)
    actor_id: Mapped[str | None] = mapped_column(String(128), default=None)
    actor_type: Mapped[str] = mapped_column(String(32), default="user")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    summary: Mapped[str] = mapped_column(String(512))
    succeeded: Mapped[bool] = mapped_column(Boolean, default=True)
    changes: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    context: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(64), default=None)
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)


__all__ = ["PromptAudit", "PromptOptimization", "PromptReport", "PromptStatistic"]
