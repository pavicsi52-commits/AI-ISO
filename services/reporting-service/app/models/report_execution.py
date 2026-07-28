"""``report_executions`` table -- one run of one report job."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ReportExecutionStatus


class ReportExecution(BaseModel):
    """One report generation run.

    ``schedule_id`` is nullable and set only for unattended runs, which
    is what makes "how many of these were scheduled vs. ad hoc?"
    answerable in analytics without a second table.
    """

    __tablename__ = "report_executions"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("report_jobs.id", ondelete="CASCADE"), index=True
    )
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("report_schedules.id", ondelete="SET NULL"), default=None, index=True
    )
    status: Mapped[ReportExecutionStatus] = mapped_column(
        String(16), default=ReportExecutionStatus.PENDING, index=True
    )
    parameter_values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    filters: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    section_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[float | None] = mapped_column(Float, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["ReportExecution"]
