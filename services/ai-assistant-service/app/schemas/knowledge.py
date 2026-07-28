"""Request/response schemas for document ingestion and RAG search.

Docs/046's own literal REST list names no ingestion or search
endpoint, yet "RAG Pipeline"/"Embedding Pipeline" are explicit
ACCEPTANCE CRITERIA and there is otherwise no way to put a document
into the knowledge base or inspect what retrieval returns. Added
directly, the same "required capability, no REST list entry"
precedent every prior AI-IOS service has established.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import DocumentSourceType, RetrievalStrategy


class DocumentIngestRequest(BaseModel):
    """Body of ``POST /ai/knowledge/documents``."""

    organization_id: UUID
    project_id: UUID | None = None
    source_type: DocumentSourceType
    title: str = Field(min_length=1, max_length=512)
    text: str = Field(min_length=1)
    external_id: str | None = Field(default=None, max_length=255)
    uri: str | None = Field(default=None, max_length=1024)
    document_metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentIngestResponse(BaseModel):
    """What ingesting one document did.

    ``skipped_unchanged`` is surfaced rather than hidden so a caller
    re-syncing a corpus can see that incremental indexing worked
    instead of wondering why nothing was re-embedded.
    """

    document_id: UUID
    title: str
    chunks_created: int
    skipped_unchanged: bool


class DocumentResponse(BaseModel):
    """One ingested document."""

    id: UUID
    organization_id: UUID
    source_type: DocumentSourceType
    external_id: str | None
    title: str
    uri: str | None
    content_hash: str
    document_metadata: dict[str, Any]


class KnowledgeSearchRequest(BaseModel):
    """Body of ``POST /ai/knowledge/search``."""

    organization_id: UUID
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    strategy: RetrievalStrategy = RetrievalStrategy.HYBRID
    source_types: list[DocumentSourceType] | None = None


class KnowledgeSearchHit(BaseModel):
    """One retrieved passage."""

    chunk_id: UUID
    document_id: UUID
    document_title: str
    document_uri: str | None
    content: str
    score: float


__all__ = [
    "DocumentIngestRequest",
    "DocumentIngestResponse",
    "DocumentResponse",
    "KnowledgeSearchHit",
    "KnowledgeSearchRequest",
]
