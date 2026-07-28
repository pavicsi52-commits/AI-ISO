"""``ai_documents`` table -- one ingested source document ("RAG":
Document Ingestion, Incremental Indexing).

``content_hash`` is what makes "Incremental Indexing" real: re-ingesting
an unchanged document is detected and skipped rather than re-chunking
and re-embedding it, which would be the dominant cost of any repeated
sync from Inventory/Runbooks/etc.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DocumentSourceType


class AiDocument(BaseModel):
    """One ingested source document."""

    __tablename__ = "ai_documents"

    source_type: Mapped[DocumentSourceType] = mapped_column(String(32), index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), default=None, index=True)
    title: Mapped[str] = mapped_column(String(512))
    uri: Mapped[str | None] = mapped_column(String(1024), default=None)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    document_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


__all__ = ["AiDocument"]
