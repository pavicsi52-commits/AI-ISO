"""``automation_executions`` table. Per docs/040 "EXECUTION MODES"/
"EVENTS": one particular run of an
:class:`~app.models.automation_job.AutomationJob`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ExecutionMode, ExecutionStatus


class AutomationExecution(BaseModel):
    """One execution run of an automation job."""

    __tablename__ = "automation_executions"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automation_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    execution_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("automation_execution_plans.id", ondelete="SET NULL"), default=None
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        String(16), default=ExecutionStatus.PENDING, index=True
    )
    execution_mode: Mapped[ExecutionMode] = mapped_column(String(24), index=True)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    variables: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    error_message: Mapped[str | None] = mapped_column(String(2048), default=None)


__all__ = ["AutomationExecution"]
