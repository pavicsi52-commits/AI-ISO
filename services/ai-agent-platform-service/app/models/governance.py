"""``agent_statistics``, ``agent_reports``, and ``agent_audit``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuditAction, ReportFormat, ReportKind, ReportStatus


class AgentStatistic(BaseModel):
    """``agent_statistics`` -- one rolled-up activity window, org-wide."""

    __tablename__ = "agent_statistics"
    __table_args__ = (Index("ix_agent_statistics_window_start", "window_start"),)

    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    active_agents: Mapped[int] = mapped_column(Integer, default=0)
    task_count: Mapped[int] = mapped_column(Integer, default=0)
    executions_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    executions_failed: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    average_cost_usd: Mapped[float | None] = mapped_column(Float, default=None)
    average_latency_ms: Mapped[float | None] = mapped_column(Float, default=None)
    memory_rows_created: Mapped[int] = mapped_column(Integer, default=0)
    by_agent_type: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    by_model_provider: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    by_tool: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)


class AgentReport(BaseModel):
    """``agent_reports`` -- one generated report."""

    __tablename__ = "agent_reports"
    __table_args__ = (Index("ix_agent_reports_kind", "kind"),)

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


class AgentAudit(BaseModel):
    """``agent_audit`` -- the append-only audit trail."""

    __tablename__ = "agent_audit"
    __table_args__ = (
        Index("ix_agent_audit_action", "action"),
        Index("ix_agent_audit_entity_id", "entity_id"),
        Index("ix_agent_audit_occurred_at", "occurred_at"),
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


__all__ = ["AgentAudit", "AgentReport", "AgentStatistic"]
