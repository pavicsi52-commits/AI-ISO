"""``change_statistics``, ``change_reports``, ``change_audit``.

The three tables that turn change history into something a leadership
review, a trend dashboard, and an auditor can each read.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuditAction, JobStatus, ReportFormat, ReportKind


class ChangeReport(BaseModel):
    """``change_reports`` -- a generated document."""

    __tablename__ = "change_reports"
    __table_args__ = (Index("ix_change_report_org", "organization_id", "generated_at"),)

    kind: Mapped[ReportKind] = mapped_column(String(32), index=True)
    report_format: Mapped[ReportFormat] = mapped_column(String(16), default=ReportFormat.JSON)
    title: Mapped[str] = mapped_column(String(512))
    status: Mapped[JobStatus] = mapped_column(String(32), default=JobStatus.PENDING, index=True)

    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    change_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("change_requests.id", ondelete="SET NULL"), default=None
    )

    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    generated_by: Mapped[str | None] = mapped_column(String(255), default=None)
    duration_ms: Mapped[float | None] = mapped_column(Float, default=None)

    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ChangeStatistic(BaseModel):
    """``change_statistics`` -- one rolled-up window."""

    __tablename__ = "change_statistics"
    __table_args__ = (Index("ix_change_statistic_org", "organization_id", "window_start"),)

    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    changes_created: Mapped[int] = mapped_column(Integer, default=0)
    changes_completed: Mapped[int] = mapped_column(Integer, default=0)
    changes_rolled_back: Mapped[int] = mapped_column(Integer, default=0)
    changes_rejected: Mapped[int] = mapped_column(Integer, default=0)
    changes_cancelled: Mapped[int] = mapped_column(Integer, default=0)
    emergency_changes: Mapped[int] = mapped_column(Integer, default=0)
    open_total: Mapped[int] = mapped_column(Integer, default=0)

    success_rate: Mapped[float] = mapped_column(Float, default=0.0)
    """``changes_completed`` over every change that reached a terminal
    outcome in the window -- rolled back, rejected, and cancelled all
    count against it, the same distinction Prompt 052 draws between
    "closed" and "resolved successfully."""

    avg_approval_duration_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    avg_implementation_duration_seconds: Mapped[float | None] = mapped_column(Float, default=None)

    conflicts_detected: Mapped[int] = mapped_column(Integer, default=0)

    by_risk_level: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    by_category: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)


class ChangeAudit(BaseModel):
    """``change_audit`` -- append-only record of who did what.

    Carries its own ``occurred_at`` rather than relying on
    ``created_at``: the base entity's timestamps describe the row, and
    an audit trail has to describe the event even if the two ever
    diverge.
    """

    __tablename__ = "change_audit"
    __table_args__ = (
        Index("ix_change_audit_org", "organization_id", "occurred_at"),
        Index("ix_change_audit_action", "organization_id", "action"),
        Index("ix_change_audit_actor", "organization_id", "actor_id"),
    )

    action: Mapped[AuditAction] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    entity_reference: Mapped[str | None] = mapped_column(String(255), default=None)

    actor_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    actor_type: Mapped[str] = mapped_column(String(32), default="user")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    summary: Mapped[str] = mapped_column(Text)
    succeeded: Mapped[bool] = mapped_column(Boolean, default=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)
    request_id: Mapped[str | None] = mapped_column(String(64), default=None)
    changes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["ChangeAudit", "ChangeReport", "ChangeStatistic"]
