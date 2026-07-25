"""``automation_audit`` table -- privileged-action audit trail. Per
docs/040 "AUDIT": Automation Creation, Execution, Cancellation,
Approval, Rollback, Configuration Changes, Target Selection,
Administrative Operations.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AuditOutcome


class AutomationAuditEntry(BaseModel):
    """One privileged/administrative action recorded against a job or execution."""

    __tablename__ = "automation_audit"

    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("automation_jobs.id", ondelete="CASCADE"), default=None, index=True
    )
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("automation_executions.id", ondelete="CASCADE"), default=None, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    action: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[AuditOutcome] = mapped_column(String(16), default=AuditOutcome.SUCCESS)
    reason: Mapped[str] = mapped_column(String(1024), default="")
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


__all__ = ["AutomationAuditEntry"]
