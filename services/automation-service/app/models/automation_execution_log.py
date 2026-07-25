"""``automation_execution_logs`` table. Per docs/040 "LOGGING"
"Capture": Execution Logs, Console Output, Structured Logs, Connector
Logs, Timing, Errors, Warnings, Execution Metadata.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import LogLevel


class AutomationExecutionLog(BaseModel):
    """One structured log line captured during an automation execution."""

    __tablename__ = "automation_execution_logs"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automation_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("automation_execution_steps.id", ondelete="SET NULL"), default=None, index=True
    )
    level: Mapped[LogLevel] = mapped_column(String(16), default=LogLevel.INFO, index=True)
    message: Mapped[str] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["AutomationExecutionLog"]
