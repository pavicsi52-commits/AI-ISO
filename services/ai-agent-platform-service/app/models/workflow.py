"""``agent_workflows``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import OrchestrationPattern, WorkflowRunStatus


class AgentWorkflow(BaseModel):
    """``agent_workflows`` -- one LangGraph-style multi-agent orchestration
    run: a compiled node/edge graph (``shared_core.workflow.nodes
    .NodeType`` values embedded in ``graph_definition``), its own
    current position, and a real, DB-persisted checkpoint --
    ``shared_core.workflow.checkpoint.CheckpointStore`` is explicitly
    in-process-only per its own docstring, so this table *is* the
    "repository layer" that docstring says real persistence needs.
    """

    __tablename__ = "agent_workflows"
    __table_args__ = (Index("ix_agent_workflow_status", "status"),)

    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), default=None, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="SET NULL"), default=None, index=True
    )
    pattern: Mapped[OrchestrationPattern] = mapped_column(
        String(24), default=OrchestrationPattern.PLANNER_EXECUTOR
    )
    status: Mapped[WorkflowRunStatus] = mapped_column(
        String(24), default=WorkflowRunStatus.PENDING, index=True
    )
    graph_definition: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    current_node_id: Mapped[str | None] = mapped_column(String(128), default=None)
    checkpoint: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    participating_agent_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["AgentWorkflow"]
