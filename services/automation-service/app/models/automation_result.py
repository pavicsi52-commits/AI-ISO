"""``automation_results`` table -- the final outcome summary for one
automation execution, computed once at completion time rather than
re-aggregated from steps/logs on every read.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column


class AutomationResult(BaseModel):
    """One final outcome summary for a completed automation execution."""

    __tablename__ = "automation_results"
    __table_args__ = (UniqueConstraint("execution_id", name="uq_automation_result_execution"),)

    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automation_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    summary: Mapped[str | None] = mapped_column(String(2048), default=None)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["AutomationResult"]
