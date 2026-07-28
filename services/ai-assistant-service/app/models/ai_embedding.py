"""``ai_embeddings`` table -- one chunk's own vector ("RAG":
Embeddings, Vector Search, Semantic Search).

Uses a **real ``pgvector`` column**, not a JSON array of floats: the
platform's own Postgres image is ``pgvector/pgvector:pg17`` (extension
``vector`` 0.8.5, verified installed), so genuine indexed
nearest-neighbour search is available and a JSON fallback would throw
away the entire point of choosing that image.

``dimensions`` is stored alongside because different providers emit
different widths (OpenAI ``text-embedding-3-small`` is 1536, many local
models are 384/768). The column itself is declared at the configured
:attr:`~app.config.settings.AiAssistantServiceSettings.embedding_dimensions`
width; a vector of a different width is rejected at write time rather
than silently corrupting a shared index, and ``provider``/``model``
record which embedder produced it so a re-index can find every vector
that needs regenerating after a model change.
"""

from __future__ import annotations

import uuid

from pgvector.sqlalchemy import Vector
from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

EMBEDDING_DIMENSIONS = 1536
"""The declared width of the ``vector`` column.

Fixed at the schema level because a pgvector column's own dimensionality
is part of its type -- it cannot vary per row. Chosen to match OpenAI's
``text-embedding-3-small``, the most common hosted default; a
deployment standardising on a narrower local model changes this
constant and regenerates the migration rather than mixing widths.
"""


class AiEmbedding(BaseModel):
    """One chunk's own embedding vector."""

    __tablename__ = "ai_embeddings"

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_chunks.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(128), index=True)
    dimensions: Mapped[int] = mapped_column(Integer, default=EMBEDDING_DIMENSIONS)
    vector: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))


__all__ = ["EMBEDDING_DIMENSIONS", "AiEmbedding"]
