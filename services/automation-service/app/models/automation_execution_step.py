"""``automation_execution_steps`` table. Per docs/040 "EXECUTION PLANS"
"Support": Pre-check Tasks, Preparation, Validation, Execution,
Post-validation, Cleanup -- each becomes one ordered step row within an
execution.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ExecutionStepStatus


class AutomationExecutionStep(BaseModel):
    """One ordered step within an automation execution."""

    __tablename__ = "automation_execution_steps"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automation_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_index: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[ExecutionStepStatus] = mapped_column(
        String(16), default=ExecutionStepStatus.PENDING, index=True
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("automation_targets.id", ondelete="SET NULL"), default=None, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    error_message: Mapped[str | None] = mapped_column(String(2048), default=None)


__all__ = ["AutomationExecutionStep"]
