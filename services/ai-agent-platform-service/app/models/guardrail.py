"""``agent_guardrails``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import GuardrailType


class AgentGuardrail(BaseModel):
    """``agent_guardrails`` -- one guardrail's own configuration and
    trigger history for an agent (``agent_id`` nullable for an
    org-wide default applied to every agent that doesn't override it).
    """

    __tablename__ = "agent_guardrails"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "agent_id", "guardrail_type", name="uq_agent_guardrail_type"
        ),
        Index("ix_agent_guardrail_type", "guardrail_type"),
    )

    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), default=None, index=True
    )
    guardrail_type: Mapped[GuardrailType] = mapped_column(String(32), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    trigger_count: Mapped[int] = mapped_column(Integer, default=0)
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )


__all__ = ["AgentGuardrail"]
