"""``ai_agents`` table -- one registered agent ("AGENT TYPES").

``tool_keys`` lists which registered tools this agent may call, which
is how "Permission-aware Tool Calls" is enforced structurally rather
than left to the model's own discretion: an agent physically cannot
invoke a tool outside its own list.
"""

from __future__ import annotations

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AgentType, ModelProvider


class AiAgent(BaseModel):
    """One registered agent."""

    __tablename__ = "ai_agents"

    name: Mapped[str] = mapped_column(String(255), index=True)
    agent_type: Mapped[AgentType] = mapped_column(String(24), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    provider: Mapped[ModelProvider] = mapped_column(String(24))
    model: Mapped[str] = mapped_column(String(128))
    system_prompt: Mapped[str | None] = mapped_column(Text, default=None)
    tool_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2048)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["AiAgent"]
