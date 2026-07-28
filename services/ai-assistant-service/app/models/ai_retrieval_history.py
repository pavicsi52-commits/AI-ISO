"""``ai_retrieval_history`` table -- what one RAG retrieval actually
returned ("RAG": Context Ranking; "ANALYTICS").

Recorded per retrieval so a later "why did the assistant say that?"
question is answerable: without it, a citation can be shown but the
ranking that produced it -- and the chunks that lost -- are gone.
"""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RetrievalStrategy


class AiRetrievalHistory(BaseModel):
    """One recorded RAG retrieval."""

    __tablename__ = "ai_retrieval_history"

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), default=None, index=True
    )
    query: Mapped[str] = mapped_column(Text)
    strategy: Mapped[RetrievalStrategy] = mapped_column(String(16), index=True)
    top_k: Mapped[int] = mapped_column(Integer, default=5)
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    duration_ms: Mapped[float | None] = mapped_column(Float, default=None)


__all__ = ["AiRetrievalHistory"]
