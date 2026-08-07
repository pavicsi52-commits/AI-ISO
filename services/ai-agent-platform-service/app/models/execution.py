"""``agent_executions``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ExecutionStatus, ModelProvider, ReasoningMode


class AgentExecution(BaseModel):
    """``agent_executions`` -- one agent run instance: model call(s),
    tool invocations, tokens, latency, and cost. Per docs/060's own
    "OBSERVABILITY" section: Planning Time, Execution Time, Token
    Usage, Model Usage, Tool Usage, Task Success/Failure, Latency,
    Resource Consumption.
    """

    __tablename__ = "agent_executions"
    __table_args__ = (Index("ix_agent_execution_status", "status"),)

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_tasks.id", ondelete="SET NULL"), default=None, index=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="SET NULL"), default=None, index=True
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        String(16), default=ExecutionStatus.PENDING, index=True
    )
    reasoning_mode: Mapped[ReasoningMode] = mapped_column(
        String(32), default=ReasoningMode.TOOL_BASED
    )
    model_provider: Mapped[ModelProvider] = mapped_column(String(20), default=ModelProvider.OLLAMA)
    model_name: Mapped[str] = mapped_column(String(128), default="llama3")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls_made: Mapped[int] = mapped_column(Integer, default=0)
    reasoning_steps: Mapped[int] = mapped_column(Integer, default=0)
    planning_ms: Mapped[float | None] = mapped_column(Float, default=None)
    latency_ms: Mapped[float | None] = mapped_column(Float, default=None)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    input_summary: Mapped[str | None] = mapped_column(Text, default=None)
    output_summary: Mapped[str | None] = mapped_column(Text, default=None)
    trace: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["AgentExecution"]
