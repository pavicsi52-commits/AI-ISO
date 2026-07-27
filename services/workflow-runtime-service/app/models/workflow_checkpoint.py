"""``workflow_checkpoints`` table -- a durable copy of one
``shared_core.workflow.checkpoint.Checkpoint``.

``shared_core.workflow.checkpoint.CheckpointStore`` is a plain
in-memory ``dict`` with no persistence of its own (confirmed: not an
ABC, nothing in the SDK subclasses it) -- ``app/checkpoints/store.py``
wraps one to also durably record every checkpoint here, which is what
actually makes "Resume"/"Restore"/"Crash Recovery"/"Distributed
Recovery" (docs/042 "CHECKPOINTING") possible at all, since the SDK's
own in-memory store is lost the moment this process restarts.

``variables_snapshot`` stores the real resolved values (including
``SECRET``-scope ones) -- a resume genuinely needs them to continue
correctly. Masking for "Secrets SHALL never appear in logs" happens at
the response-schema layer (``GET /workflow-instances/{id}/checkpoints``
never echoes ``variables_snapshot`` back), not by omitting real values
here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import CheckpointType, WorkflowInstanceStatus


class WorkflowCheckpoint(BaseModel):
    """One durable snapshot of a workflow instance's own execution progress."""

    __tablename__ = "workflow_checkpoints"

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    checkpoint_type: Mapped[CheckpointType] = mapped_column(
        String(16), default=CheckpointType.AUTOMATIC
    )
    state: Mapped[WorkflowInstanceStatus] = mapped_column(String(16))
    completed_node_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    variables_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    checkpointed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["WorkflowCheckpoint"]
