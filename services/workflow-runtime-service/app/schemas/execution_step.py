"""Response schema for :class:`~app.models.workflow_execution_step.WorkflowExecutionStep`."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from shared_core.workflow import NodeType

from app.models.enums import NodeExecutionStatus


class WorkflowExecutionStepResponse(BaseModel):
    """One node's own execution result within a workflow instance."""

    id: UUID
    instance_id: UUID
    node_id: str
    node_type: NodeType
    status: NodeExecutionStatus
    started_at: datetime | None
    finished_at: datetime | None
    output: Any | None
    error: str | None
    attempts: int


__all__ = ["WorkflowExecutionStepResponse"]
