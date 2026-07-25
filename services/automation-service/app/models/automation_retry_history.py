"""``automation_retry_history`` table. Per docs/040 "RETRY" "Support":
Immediate Retry, Delayed Retry, Exponential Backoff, Retry Policies,
Retry Limits, Failure Classification.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import FailureClassification, RetryStrategy


class AutomationRetryHistory(BaseModel):
    """One retry attempt recorded against an execution (or one of its steps)."""

    __tablename__ = "automation_retry_history"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automation_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("automation_execution_steps.id", ondelete="SET NULL"), default=None, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer)
    strategy: Mapped[RetryStrategy] = mapped_column(String(24), index=True)
    classification: Mapped[FailureClassification | None] = mapped_column(String(24), default=None)
    succeeded: Mapped[bool] = mapped_column(Boolean, default=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["AutomationRetryHistory"]
