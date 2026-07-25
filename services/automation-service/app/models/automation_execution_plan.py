"""``automation_execution_plans`` table. Per docs/040 "EXECUTION PLANS"
"Support": Pre-check Tasks, Preparation, Validation, Execution,
Post-validation, Cleanup, Notifications, Rollback Planning, Approval
Gates -- one reusable, ordered plan a job can be attached to.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column


class AutomationExecutionPlan(BaseModel):
    """One reusable, ordered execution plan (phases plus approval/rollback shape)."""

    __tablename__ = "automation_execution_plans"

    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("automation_jobs.id", ondelete="SET NULL"), default=None, index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    approval_gates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    rollback_plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


__all__ = ["AutomationExecutionPlan"]
