"""``ai_statistics`` table -- one organization's cached analytics
rollup. Per docs/046 "ANALYTICS": Conversation Count, Tool Usage, Agent
Usage, Model Usage, Latency, Cost, Token Usage, Recommendation
Accuracy, Feedback Scores.

``estimated_cost_usd`` is named *estimated* deliberately: cost is
derived from token counts against a configured price table, not
reported by any provider's own billing API, and pretending otherwise
would misrepresent its accuracy.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column


class AiStatistics(BaseModel):
    """One organization's cached AI analytics rollup."""

    __tablename__ = "ai_statistics"

    total_conversations: Mapped[int] = mapped_column(Integer, default=0)
    total_messages: Mapped[int] = mapped_column(Integer, default=0)
    total_tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    total_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    average_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    positive_feedback_rate: Mapped[float] = mapped_column(Float, default=0.0)
    recommendation_acceptance_rate: Mapped[float] = mapped_column(Float, default=0.0)
    tool_usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    agent_usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model_usage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["AiStatistics"]
