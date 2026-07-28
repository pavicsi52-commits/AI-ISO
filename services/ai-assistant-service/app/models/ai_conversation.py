"""``ai_conversations`` table -- one chat thread between a user and the
assistant. ``session_id`` is nullable: a conversation may be started
directly (``POST /ai/chat``) without an explicit session of its own.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ConversationStatus


class AiConversation(BaseModel):
    """One chat thread."""

    __tablename__ = "ai_conversations"

    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_sessions.id", ondelete="SET NULL"), default=None, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[ConversationStatus] = mapped_column(
        String(16), default=ConversationStatus.ACTIVE, index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["AiConversation"]
