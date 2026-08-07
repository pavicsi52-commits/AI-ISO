"""``agent_evaluations``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column


class AgentEvaluation(BaseModel):
    """``agent_evaluations`` -- one scored evaluation of a specific
    execution, per docs/060's own "EVALUATION" section: Task Accuracy,
    Execution Quality, Reasoning Quality, Tool Success Rate, Latency,
    Cost, Human Feedback, Regression Tests. Stored as direct float
    columns rather than a metric-name/value pair table, since the
    metric set is fixed and every evaluation always scores all of them.
    """

    __tablename__ = "agent_evaluations"
    __table_args__ = (Index("ix_agent_evaluation_execution", "execution_id"),)

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_executions.id", ondelete="CASCADE"), index=True
    )
    task_accuracy: Mapped[float | None] = mapped_column(Float, default=None)
    execution_quality: Mapped[float | None] = mapped_column(Float, default=None)
    reasoning_quality: Mapped[float | None] = mapped_column(Float, default=None)
    tool_success_rate: Mapped[float | None] = mapped_column(Float, default=None)
    latency_ms: Mapped[float | None] = mapped_column(Float, default=None)
    cost_usd: Mapped[float | None] = mapped_column(Float, default=None)
    human_feedback_score: Mapped[float | None] = mapped_column(Float, default=None)
    is_regression_test: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    evaluated_by: Mapped[str | None] = mapped_column(String(128), default=None)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["AgentEvaluation"]
