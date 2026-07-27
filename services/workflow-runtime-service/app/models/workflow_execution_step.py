"""``workflow_execution_steps`` table -- one node's own execution result
within a running instance.

Maps 1:1 from ``shared_core.workflow.execution.NodeExecutionResult``,
persisted as each level of the DAG completes (via the engine's own
``on_event`` hook -- see ``app/services/execution.py``) so
``GET /workflow-instances/{id}`` can show live per-node progress
without waiting for the whole run to finish, since
``WorkflowEngine.run()`` only returns its final, in-memory
``WorkflowExecution`` after the entire DAG completes or fails.
``node_type`` reuses ``shared_core.workflow.NodeType`` directly -- see
``app/models/enums.py``'s own docstring for why.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from shared_core.workflow import NodeType
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import NodeExecutionStatus


class WorkflowExecutionStep(BaseModel):
    """One node's own execution result within a workflow instance."""

    __tablename__ = "workflow_execution_steps"

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(String(255), index=True)
    node_type: Mapped[NodeType] = mapped_column(String(32))
    status: Mapped[NodeExecutionStatus] = mapped_column(
        String(16), default=NodeExecutionStatus.PENDING, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    output: Mapped[Any | None] = mapped_column(JSON, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    attempts: Mapped[int] = mapped_column(Integer, default=1)


__all__ = ["WorkflowExecutionStep"]
