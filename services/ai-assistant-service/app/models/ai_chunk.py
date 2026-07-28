"""``ai_chunks`` table -- one retrievable passage of a document
("RAG": Chunking, Citation Support).

The chunk's own text lives here rather than being re-read from the
source at query time, because a citation must show what was actually
retrieved -- a source that changed since indexing would otherwise make
citations silently wrong.
"""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column


class AiChunk(BaseModel):
    """One retrievable passage of a document."""

    __tablename__ = "ai_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_documents.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)


__all__ = ["AiChunk"]
