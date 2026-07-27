"""Response schema for :class:`~app.models.workflow_log.WorkflowLog`,
backing ``GET /workflow-instances/{id}/logs``.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class WorkflowLogResponse(BaseModel):
    """One structured log line recorded during a workflow instance's own run."""

    id: UUID
    instance_id: UUID
    node_id: str | None
    level: str
    message: str
    logged_at: datetime


__all__ = ["WorkflowLogResponse"]
