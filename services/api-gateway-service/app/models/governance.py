"""``api_statistics``, ``api_reports``, ``api_audit``."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuditAction, ReportFormat, ReportKind, ReportStatus


class ApiStatistic(BaseModel):
    """``api_statistics`` -- one rolled-up reporting window."""

    __tablename__ = "api_statistics"
    __table_args__ = (
        UniqueConstraint("organization_id", "window_start", name="uq_api_statistic_window"),
    )

    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    total_requests: Mapped[int] = mapped_column(Integer, default=0)
    successful_requests: Mapped[int] = mapped_column(Integer, default=0)
    failed_requests: Mapped[int] = mapped_column(Integer, default=0)
    rate_limited_requests: Mapped[int] = mapped_column(Integer, default=0)
    quota_exceeded_requests: Mapped[int] = mapped_column(Integer, default=0)

    average_latency_ms: Mapped[float | None] = mapped_column(Float, default=None)
    p95_latency_ms: Mapped[float | None] = mapped_column(Float, default=None)
    error_rate: Mapped[float] = mapped_column(Float, default=0.0)
    success_rate: Mapped[float] = mapped_column(Float, default=100.0)

    by_service: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    by_status_code: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    by_client: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)


class ApiReport(BaseModel):
    """``api_reports`` -- one generated document."""

    __tablename__ = "api_reports"

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


class ApiAudit(BaseModel):
    """``api_audit`` -- the append-only audit trail."""

    __tablename__ = "api_audit"

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


__all__ = ["ApiAudit", "ApiReport", "ApiStatistic"]
