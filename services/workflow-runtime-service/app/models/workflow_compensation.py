"""``workflow_compensation`` table -- one recorded compensation (Saga
pattern) action outcome.

Per docs/042 "COMPENSATION" "Support": Saga Pattern, Compensation
Actions, Compensation Queue, Retry Compensation, Failure Recovery,
Compensation Audit. Compensation *actions themselves* are Python
closures registered per-node-id at process startup into a
``shared_core.workflow.compensation.CompensationRegistry`` (see
``app/handlers/compensation.py``) -- this table is the audit record of
what actually happened when ``shared_core.workflow.rollback
.rollback_workflow`` invoked one, never the action's own logic.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from shared_core.workflow import NodeType
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import CompensationStatus


class WorkflowCompensation(BaseModel):
    """One recorded compensation action outcome for a workflow instance."""

    __tablename__ = "workflow_compensation"

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(String(255), index=True)
    node_type: Mapped[NodeType] = mapped_column(String(32))
    status: Mapped[CompensationStatus] = mapped_column(
        String(16), default=CompensationStatus.PENDING
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["WorkflowCompensation"]
