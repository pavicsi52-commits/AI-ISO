"""``automation_rollbacks`` table. Per docs/040 "ROLLBACK" "Support":
Step Rollback, Execution Rollback, Configuration Rollback, Playbook
Rollback, Automatic Rollback, Manual Rollback, Rollback Validation,
Rollback Reports.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RollbackStatus, RollbackType


class AutomationRollback(BaseModel):
    """One rollback operation against an automation execution."""

    __tablename__ = "automation_rollbacks"

    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("automation_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rollback_type: Mapped[RollbackType] = mapped_column(String(16), index=True)
    status: Mapped[RollbackStatus] = mapped_column(
        String(16), default=RollbackStatus.PENDING, index=True
    )
    initiated_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    reason: Mapped[str | None] = mapped_column(String(1024), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["AutomationRollback"]
