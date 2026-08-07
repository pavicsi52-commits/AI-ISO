"""``agent_memory``."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import MemoryScope


class AgentMemory(BaseModel):
    """``agent_memory`` -- one scoped memory row, most-specific-scope-first
    (``TASK`` > ``CONVERSATION`` > ``SESSION`` > ``SHORT_TERM`` >
    ``LONG_TERM`` > ``KNOWLEDGE_REFERENCE``), mirroring
    ``ai-assistant-service``'s own ``AiMemory`` shape.

    No database-level uniqueness on ``(agent_id, scope, key)``, matching
    ``AiMemory``'s own precedent: a DB constraint on those three columns
    alone would be *wrong* here, not just redundant -- ``TASK`` and
    ``SESSION`` scoped rows are additionally distinguished by
    ``task_id``/``session_id``, and Postgres treats every ``NULL`` in a
    unique constraint as distinct, so a constraint naming those columns
    would silently fail to enforce anything for the agent-wide scopes
    (``SHORT_TERM``/``LONG_TERM``/``KNOWLEDGE_REFERENCE``) that never
    set them. Uniqueness is instead a service-level "look up by key
    first, then create-or-update" rule
    (:meth:`~app.services.memory.MemoryService.remember`), the same
    place ``AiMemory``'s own precedent enforces it.
    """

    __tablename__ = "agent_memory"
    __table_args__ = (Index("ix_agent_memory_expires_at", "expires_at"),)

    agent_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), index=True
    )
    scope: Mapped[MemoryScope] = mapped_column(String(24), index=True)
    key: Mapped[str] = mapped_column(String(255))
    content: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    session_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["AgentMemory"]
