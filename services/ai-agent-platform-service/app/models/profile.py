"""``agent_profiles``."""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ModelProvider, ReasoningMode, RoutingStrategy


class AgentProfile(BaseModel):
    """``agent_profiles`` -- one agent's own persona/model/reasoning
    configuration -- docs/060's own "AGENT LIFECYCLE" > "Configuration"
    stage. One active profile per agent, updated in place; each
    activation snapshots it into a new ``AgentVersion.profile_snapshot``.
    """

    __tablename__ = "agent_profiles"
    __table_args__ = (UniqueConstraint("agent_id", name="uq_agent_profile_agent"),)

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    system_prompt: Mapped[str | None] = mapped_column(Text, default=None)
    model_provider: Mapped[ModelProvider] = mapped_column(String(20), default=ModelProvider.OLLAMA)
    model_name: Mapped[str] = mapped_column(String(128), default="llama3")
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    max_tokens: Mapped[int] = mapped_column(Integer, default=2_048)
    reasoning_mode: Mapped[ReasoningMode] = mapped_column(
        String(32), default=ReasoningMode.TOOL_BASED
    )
    routing_strategy: Mapped[RoutingStrategy] = mapped_column(
        String(20), default=RoutingStrategy.FALLBACK
    )
    fallback_providers: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_tool_keys: Mapped[list[str]] = mapped_column(JSON, default=list)
    max_reasoning_steps: Mapped[int] = mapped_column(Integer, default=8)
    extra_config: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)


__all__ = ["AgentProfile"]
