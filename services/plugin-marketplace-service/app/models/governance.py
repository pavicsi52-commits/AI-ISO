"""``plugin_statistics``, ``plugin_reports``, and ``plugin_audit``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuditAction, ReportFormat, ReportKind, ReportStatus


class PluginStatistic(BaseModel):
    """``plugin_statistics`` -- one rolled-up marketplace activity window, org-wide."""

    __tablename__ = "plugin_statistics"
    __table_args__ = (Index("ix_plugin_statistics_window_start", "window_start"),)

    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    plugins_published: Mapped[int] = mapped_column(Integer, default=0)
    installations_attempted: Mapped[int] = mapped_column(Integer, default=0)
    installations_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    installations_failed: Mapped[int] = mapped_column(Integer, default=0)
    upgrades_completed: Mapped[int] = mapped_column(Integer, default=0)
    rollbacks_completed: Mapped[int] = mapped_column(Integer, default=0)
    reviews_submitted: Mapped[int] = mapped_column(Integer, default=0)
    average_rating: Mapped[float | None] = mapped_column(Float, default=None)
    by_category: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)


class PluginReport(BaseModel):
    """``plugin_reports`` -- one generated report."""

    __tablename__ = "plugin_reports"
    __table_args__ = (Index("ix_plugin_reports_kind", "kind"),)

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


class PluginAudit(BaseModel):
    """``plugin_audit`` -- the append-only audit trail."""

    __tablename__ = "plugin_audit"
    __table_args__ = (
        Index("ix_plugin_audit_action", "action"),
        Index("ix_plugin_audit_entity_id", "entity_id"),
        Index("ix_plugin_audit_occurred_at", "occurred_at"),
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


__all__ = ["PluginAudit", "PluginReport", "PluginStatistic"]
