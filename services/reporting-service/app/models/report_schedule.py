"""``report_schedules`` table -- when a report job runs unattended."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ExportFormat, ScheduleFrequency


class ReportSchedule(BaseModel):
    """One schedule attached to a report job.

    ``timezone`` is stored per schedule rather than assumed UTC because
    "every Monday 09:00" means a different instant in Berlin than in
    Chicago, and a compliance report that silently drifts an hour twice
    a year is worse than no schedule at all.
    """

    __tablename__ = "report_schedules"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("report_jobs.id", ondelete="CASCADE"), index=True
    )
    frequency: Mapped[ScheduleFrequency] = mapped_column(String(16), index=True)
    cron_expression: Mapped[str | None] = mapped_column(String(128), default=None)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    export_format: Mapped[ExportFormat] = mapped_column(String(16), default=ExportFormat.PDF)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    notify_on_failure: Mapped[bool] = mapped_column(Boolean, default=True)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


__all__ = ["ReportSchedule"]
