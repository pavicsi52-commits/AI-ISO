"""``agent_tasks``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import TaskPriority, TaskStatus


class AgentTask(BaseModel):
    """``agent_tasks`` -- one unit of work queued for (or assigned to) an
    agent, covering docs/060's own "TASK MANAGEMENT" section in full:
    Creation, Queue, Assignment, Priority, Dependencies (via
    ``parent_task_id``), Scheduling, Retry, Cancellation, Timeout,
    Checkpointing.
    """

    __tablename__ = "agent_tasks"
    __table_args__ = (
        Index("ix_agent_task_status", "status"),
        Index("ix_agent_task_scheduled_at", "scheduled_at"),
    )

    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), default=None, index=True
    )
    """Nullable: a freshly-created task may not yet be assigned to an agent."""
    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="SET NULL"), default=None, index=True
    )
    task_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[TaskStatus] = mapped_column(String(16), default=TaskStatus.PENDING, index=True)
    priority: Mapped[TaskPriority] = mapped_column(String(16), default=TaskPriority.NORMAL)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, object] | None] = mapped_column(JSON, default=None)
    checkpoint: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    timeout_seconds: Mapped[float] = mapped_column(Float, default=300.0)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    requested_by: Mapped[str | None] = mapped_column(String(128), default=None)


__all__ = ["AgentTask"]
