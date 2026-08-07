"""``agent_sessions``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import SessionStatus


class AgentSession(BaseModel):
    """``agent_sessions`` -- one conversation/interaction session with an agent."""

    __tablename__ = "agent_sessions"
    __table_args__ = (Index("ix_agent_session_status", "status"),)

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[SessionStatus] = mapped_column(
        String(16), default=SessionStatus.ACTIVE, index=True
    )
    context: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    initiated_by: Mapped[str | None] = mapped_column(String(128), default=None)


__all__ = ["AgentSession"]
