"""``scheduler_statistics``, ``scheduler_reports``, ``scheduler_audit``."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuditAction, ReportFormat, ReportKind, ReportStatus


class SchedulerStatistic(BaseModel):
    """``scheduler_statistics`` -- one rolled-up reporting window."""

    __tablename__ = "scheduler_statistics"
    __table_args__ = (
        UniqueConstraint("organization_id", "window_start", name="uq_scheduler_statistic_window"),
    )

    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    jobs_scheduled: Mapped[int] = mapped_column(Integer, default=0)
    jobs_completed: Mapped[int] = mapped_column(Integer, default=0)
    jobs_failed: Mapped[int] = mapped_column(Integer, default=0)
    jobs_cancelled: Mapped[int] = mapped_column(Integer, default=0)

    retry_rate: Mapped[float] = mapped_column(Float, default=0.0)
    avg_queue_length: Mapped[float] = mapped_column(Float, default=0.0)
    avg_execution_time_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    average_delay_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    success_rate: Mapped[float] = mapped_column(Float, default=100.0)
    scheduler_availability: Mapped[float | None] = mapped_column(Float, default=None)

    by_job_type: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    by_priority: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)


class SchedulerReport(BaseModel):
    """``scheduler_reports`` -- one generated document."""

    __tablename__ = "scheduler_reports"

    kind: Mapped[ReportKind] = mapped_column(String(32), index=True)
    report_format: Mapped[ReportFormat] = mapped_column(String(16), default=ReportFormat.JSON)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[ReportStatus] = mapped_column(String(32), default=ReportStatus.PENDING)

    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    row_count: Mapped[int | None] = mapped_column(Integer, default=None)
    generated_by: Mapped[str | None] = mapped_column(String(255), default=None)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    duration_ms: Mapped[float | None] = mapped_column(Float, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)


class SchedulerAudit(BaseModel):
    """``scheduler_audit`` -- the append-only audit trail."""

    __tablename__ = "scheduler_audit"

    action: Mapped[AuditAction] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    entity_reference: Mapped[str | None] = mapped_column(String(255), default=None)
    actor_id: Mapped[str | None] = mapped_column(String(255), default=None)
    actor_type: Mapped[str] = mapped_column(String(32), default="user")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    summary: Mapped[str] = mapped_column(Text)
    succeeded: Mapped[bool] = mapped_column(Boolean, default=True)
    changes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    request_id: Mapped[str | None] = mapped_column(String(64), default=None)
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)


__all__ = ["SchedulerAudit", "SchedulerReport", "SchedulerStatistic"]
