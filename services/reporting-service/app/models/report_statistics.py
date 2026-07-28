"""``report_statistics`` table -- one analytics rollup per organization."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column


class ReportStatistics(BaseModel):
    """An organization's own reporting analytics.

    One row per organization, updated in place. A time series of
    snapshots would be a different (and much larger) design; docs/047's
    "ANALYTICS" list is a current-state summary, and
    :class:`app.models.report_execution.ReportExecution` already holds
    the per-run history any trend would be computed from.
    """

    __tablename__ = "report_statistics"

    total_reports: Mapped[int] = mapped_column(Integer, default=0)
    total_executions: Mapped[int] = mapped_column(Integer, default=0)
    successful_executions: Mapped[int] = mapped_column(Integer, default=0)
    failed_executions: Mapped[int] = mapped_column(Integer, default=0)
    scheduled_executions: Mapped[int] = mapped_column(Integer, default=0)
    total_downloads: Mapped[int] = mapped_column(Integer, default=0)
    total_distributions: Mapped[int] = mapped_column(Integer, default=0)
    failed_distributions: Mapped[int] = mapped_column(Integer, default=0)
    average_duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    popular_reports: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    export_format_usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    template_usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    schedule_usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    distribution_usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["ReportStatistics"]
