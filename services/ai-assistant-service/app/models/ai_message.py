"""``ai_messages`` table -- one turn in a conversation.

Token counts, ``latency_ms``, ``model``, and ``provider`` are recorded
per message because docs/046's own ANALYTICS section requires Token
Usage, Latency, Model Usage, and Cost -- all per-turn facts that cannot
be reconstructed after the fact from the conversation alone.

Ordering is by ``sequence``, not by a timestamp of its own: the
inherited ``BaseEntityMixin.created_at`` already records when a row was
written, and two turns can share a wall-clock millisecond, so an
explicit monotonic sequence is what actually defines turn order.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import MessageRole


class AiMessage(BaseModel):
    """One turn in a conversation."""

    __tablename__ = "ai_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    role: Mapped[MessageRole] = mapped_column(String(16), index=True)
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(128), default=None)
    provider: Mapped[str | None] = mapped_column(String(32), default=None)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[float | None] = mapped_column(Float, default=None)
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


__all__ = ["AiMessage"]
