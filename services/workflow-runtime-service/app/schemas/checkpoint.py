"""Response schema for :class:`~app.models.workflow_checkpoint.WorkflowCheckpoint`.

Deliberately omits ``variables_snapshot`` -- a checkpoint's real
resolved values (including ``SECRET``-scope ones) must exist in the
database for "Resume"/"Restore" to work correctly, but docs/042's own
"SECRETS: Secrets SHALL never appear in logs" extends, as a defensive
practice, to never echoing them back over a REST response either.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import CheckpointType, WorkflowInstanceStatus


class WorkflowCheckpointResponse(BaseModel):
    """One durable snapshot of a workflow instance's own execution progress."""

    id: UUID
    instance_id: UUID
    checkpoint_type: CheckpointType
    state: WorkflowInstanceStatus
    completed_node_ids: list[str]
    checkpointed_at: datetime


__all__ = ["WorkflowCheckpointResponse"]
