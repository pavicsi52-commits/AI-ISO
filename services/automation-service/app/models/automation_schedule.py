"""``automation_schedules`` table. Per docs/040 "EXECUTION MODES"
"Scheduled" -- a recurring cron trigger for a job, dispatched through
``shared_core.scheduler`` (Prompt 026) rather than a custom cron engine.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class AutomationSchedule(BaseModel):
    """One recurring cron schedule for an automation job."""

    __tablename__ = "automation_schedules"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automation_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cron_expression: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["AutomationSchedule"]
