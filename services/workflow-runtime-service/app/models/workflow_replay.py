"""``workflow_replay`` table -- one record of replaying a workflow
instance.

Per docs/042 "REPLAY" "Support": Replay Workflow, Replay Failed Steps,
Replay From Checkpoint, Replay History, Execution Comparison, Replay
Validation. A replay always produces a genuinely new
:class:`~app.models.workflow_instance.WorkflowInstance` row
(``new_instance_id``) rather than mutating the original -- "Execution
Comparison" needs two distinct, independently queryable instances to
compare, and re-running in place would destroy the original's own
history.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ReplayType


class WorkflowReplay(BaseModel):
    """One record of replaying a workflow instance as a new run."""

    __tablename__ = "workflow_replay"

    instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    new_instance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    replay_type: Mapped[ReplayType] = mapped_column(String(16))
    source_checkpoint_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workflow_checkpoints.id", ondelete="SET NULL"), default=None
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    comparison: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


__all__ = ["WorkflowReplay"]
