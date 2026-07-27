"""``workflow_states`` table -- one recorded state transition.

Distinct from ``WorkflowInstance.status`` (the instance's own *current*
state): this table is the append-only transition history,
mirroring ``shared_core.workflow.state_machine.StateMachine.history``'s
own in-memory list, persisted so it survives past a single
``WorkflowEngine.run()`` call and is queryable independently (per
docs/042 "AUDIT" "State Changes").
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import WorkflowInstanceStatus


class WorkflowStateTransition(BaseModel):
    """One recorded state transition for a workflow instance."""

    __tablename__ = "workflow_states"

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[WorkflowInstanceStatus | None] = mapped_column(String(16), default=None)
    to_status: Mapped[WorkflowInstanceStatus] = mapped_column(String(16))
    transitioned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["WorkflowStateTransition"]
