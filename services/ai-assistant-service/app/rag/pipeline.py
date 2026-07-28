"""The RAG pipeline: ingestion and retrieval.

**Ingestion** hashes the source, skips it if unchanged ("Incremental
Indexing"), otherwise chunks it, embeds every chunk, and stores both.
Re-ingesting a *changed* document replaces its chunks and vectors
rather than accumulating stale ones beside the new.

**Retrieval** runs vector search, keyword search, or both ("Hybrid
Search"), fuses hybrid results by Reciprocal Rank Fusion, and returns
ranked passages carrying everything a citation needs.

Every database write here is sequential. ``AsyncSession`` is not safe
for concurrent use by multiple asyncio tasks even for reads -- the real
production bug ``services/validation-service`` hit and every service
since has designed around. Embedding *generation* is batched into one
provider call instead, which is where the latency actually is.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.ai import AIError

from app.clients.embedding_client import EmbeddingClient
from app.embeddings.encoder import HashingEncoder, tokenize
from app.models.ai_chunk import AiChunk
from app.models.ai_document import AiDocument
from app.models.ai_embedding import AiEmbedding
from app.models.ai_retrieval_history import AiRetrievalHistory
from app.models.enums import DocumentSourceType, RetrievalStrategy
from app.rag.chunking import chunk_text
from app.repositories.ai_chunk import AiChunkRepository
from app.repositories.ai_document import AiDocumentRepository
from app.repositories.ai_embedding import AiEmbeddingRepository, SimilarChunk
from app.repositories.ai_retrieval_history import AiRetrievalHistoryRepository

RRF_K = 60
"""Reciprocal Rank Fusion damping constant.

60 is the value from the original RRF paper and the de facto standard;
it decides how sharply top ranks dominate. Named rather than inlined so
the choice is visible and tunable.
"""


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """What ingesting one document actually did."""

    document: AiDocument
    chunks_created: int
    skipped_unchanged: bool


@dataclass(frozen=True, slots=True)
class RetrievedPassage:
    """One ranked passage, with everything a citation needs."""

    chunk_id: UUID
    document_id: UUID
    document_title: str
    document_uri: str | None
    content: str
    score: float

    def as_citation(self) -> dict[str, Any]:
        """The citation shape stored on a message or recommendation."""
        return {
            "chunk_id": str(self.chunk_id),
            "document_id": str(self.document_id),
            "title": self.document_title,
            "uri": self.document_uri,
            "score": round(self.score, 6),
        }


def content_hash(text: str) -> str:
    """Stable SHA-256 of a document's own text.

    SHA-256 rather than :func:`hash` for the same reason fingerprinting
    uses it elsewhere in this platform: Python's own hash is salted per
    process, so it would report every document as changed after a
    restart and re-embed the entire corpus.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class RagPipeline:
    """Ingests documents and retrieves passages for a query."""

    def __init__(
        self,
        documents: AiDocumentRepository,
        chunks: AiChunkRepository,
        embeddings: AiEmbeddingRepository,
        retrieval_history: AiRetrievalHistoryRepository,
        encoder: HashingEncoder,
        *,
        embedding_client: EmbeddingClient | None,
        embedding_provider: str,
        embedding_model: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        self._documents = documents
        self._chunks = chunks
        self._embeddings = embeddings
        self._retrieval_history = retrieval_history
        self._encoder = encoder
        self._embedding_client = embedding_client
        self._embedding_provider = embedding_provider
        self._embedding_model = embedding_model
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        """Embed *texts*, via the provider if configured or locally.

        Raises:
            AIError: If a provider returns vectors of a width other
                than the one the ``vector`` column is declared at --
                storing them would corrupt the shared index, so this
                fails loudly rather than silently.
        """
        if not texts:
            return []
        if self._embedding_client is None:
            return [self._encoder.encode(text) for text in texts]

        vectors = await self._embedding_client.embed(texts, model=self._embedding_model)
        expected = self._encoder.dimensions
        for vector in vectors:
            if len(vector) != expected:
                raise AIError(
                    f"Embedding provider {self._embedding_provider!r} returned "
                    f"{len(vector)}-dimensional vectors, but the ai_embeddings.vector "
                    f"column is declared at {expected}. Reconfigure the embedding model "
                    "or regenerate the schema at the matching width."
                )
        return vectors

    async def ingest(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        source_type: DocumentSourceType,
        title: str,
        text: str,
        external_id: str | None = None,
        uri: str | None = None,
        document_metadata: dict[str, Any] | None = None,
    ) -> IngestionResult:
        """Ingest one document, skipping it if its content is unchanged."""
        digest = content_hash(text)

        existing = (
            await self._documents.get_by_external_id(organization_id, source_type, external_id)
            if external_id
            else await self._documents.get_by_content_hash(organization_id, digest)
        )
        if existing is not None and existing.content_hash == digest:
            return IngestionResult(document=existing, chunks_created=0, skipped_unchanged=True)

        if existing is not None:
            # Content changed: drop the stale chunks and their vectors
            # before writing the new ones, or retrieval would rank
            # against text that no longer exists.
            for stale in await self._chunks.list_for_document(existing.id):
                await self._embeddings.delete_for_chunk(stale.id)
            await self._chunks.delete_for_document(existing.id)
            existing.title = title
            existing.uri = uri
            existing.content_hash = digest
            existing.document_metadata = document_metadata or {}
            document = await self._documents.update(existing)
        else:
            document = await self._documents.create(
                AiDocument(
                    organization_id=organization_id,
                    project_id=project_id,
                    source_type=source_type,
                    external_id=external_id,
                    title=title,
                    uri=uri,
                    content_hash=digest,
                    document_metadata=document_metadata or {},
                )
            )

        pieces = chunk_text(text, chunk_size=self._chunk_size, overlap=self._chunk_overlap)
        vectors = await self._embed([piece.content for piece in pieces])

        for piece, vector in zip(pieces, vectors, strict=True):
            chunk = await self._chunks.create(
                AiChunk(
                    organization_id=organization_id,
                    project_id=project_id,
                    document_id=document.id,
                    sequence=piece.sequence,
                    content=piece.content,
                    token_estimate=piece.token_estimate,
                )
            )
            await self._embeddings.create(
                AiEmbedding(
                    organization_id=organization_id,
                    project_id=project_id,
                    chunk_id=chunk.id,
                    provider=self._embedding_provider,
                    model=self._embedding_model,
                    dimensions=len(vector),
                    vector=vector,
                )
            )

        return IngestionResult(
            document=document, chunks_created=len(pieces), skipped_unchanged=False
        )

    async def retrieve(
        self,
        organization_id: UUID,
        query: str,
        *,
        top_k: int = 5,
        strategy: RetrievalStrategy = RetrievalStrategy.HYBRID,
        source_types: list[DocumentSourceType] | None = None,
        conversation_id: UUID | None = None,
    ) -> list[RetrievedPassage]:
        """Retrieve the passages most relevant to *query*, and record it."""
        started = datetime.now(UTC)

        vector_hits: list[SimilarChunk] = []
        if strategy in (RetrievalStrategy.VECTOR, RetrievalStrategy.HYBRID):
            (query_vector,) = await self._embed([query])
            vector_hits = await self._embeddings.search_similar(
                organization_id,
                query_vector,
                top_k=top_k,
                model=self._embedding_model,
                source_types=source_types,
            )

        keyword_ids: list[UUID] = []
        keyword_by_id: dict[UUID, AiChunk] = {}
        if strategy in (RetrievalStrategy.KEYWORD, RetrievalStrategy.HYBRID):
            matches = await self._chunks.search_keyword(
                organization_id,
                tokenize(query),
                limit=top_k * 2,
                source_types=source_types,
            )
            keyword_ids = [match.id for match in matches]
            keyword_by_id = {match.id: match for match in matches}

        passages = await self._fuse(
            organization_id, strategy, vector_hits, keyword_ids, keyword_by_id, top_k
        )

        await self._retrieval_history.create(
            AiRetrievalHistory(
                organization_id=organization_id,
                conversation_id=conversation_id,
                query=query,
                strategy=strategy,
                top_k=top_k,
                results=[passage.as_citation() for passage in passages],
                duration_ms=(datetime.now(UTC) - started).total_seconds() * 1000,
            )
        )
        return passages

    async def _fuse(
        self,
        organization_id: UUID,
        strategy: RetrievalStrategy,
        vector_hits: list[SimilarChunk],
        keyword_ids: list[UUID],
        keyword_by_id: dict[UUID, AiChunk],
        top_k: int,
    ) -> list[RetrievedPassage]:
        """Combine the two result lists into one ranking.

        Pure vector or pure keyword retrieval keeps its own natural
        score. Hybrid uses Reciprocal Rank Fusion rather than mixing raw
        scores, because a cosine similarity and an ``ILIKE`` match are
        not on a comparable scale -- RRF combines *ranks*, which are.
        """
        if strategy is RetrievalStrategy.VECTOR:
            return [_from_similar(hit, hit.similarity) for hit in vector_hits][:top_k]

        if strategy is RetrievalStrategy.KEYWORD:
            return await self._passages_for_ids(organization_id, keyword_ids[:top_k])

        scores: dict[UUID, float] = {}
        for rank, vector_hit in enumerate(vector_hits):
            scores[vector_hit.chunk_id] = scores.get(vector_hit.chunk_id, 0.0) + 1.0 / (
                RRF_K + rank + 1
            )
        for rank, chunk_id in enumerate(keyword_ids):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)

        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
        by_vector_id = {vector_hit.chunk_id: vector_hit for vector_hit in vector_hits}

        # Resolve, in one pass, the keyword-only hits that need a
        # database read; vector hits already carry everything a
        # citation needs.
        keyword_only = [
            chunk_id
            for chunk_id, _ in ordered
            if chunk_id not in by_vector_id and chunk_id in keyword_by_id
        ]
        resolved = (
            {
                passage.chunk_id: passage
                for passage in await self._passages_for_ids(organization_id, keyword_only)
            }
            if keyword_only
            else {}
        )

        passages: list[RetrievedPassage] = []
        for chunk_id, score in ordered:
            matched_vector = by_vector_id.get(chunk_id)
            if matched_vector is not None:
                passages.append(_from_similar(matched_vector, score))
                continue
            keyword_passage = resolved.get(chunk_id)
            if keyword_passage is not None:
                passages.append(_rescored(keyword_passage, score))
        return passages

    async def _passages_for_ids(
        self, organization_id: UUID, chunk_ids: list[UUID]
    ) -> list[RetrievedPassage]:
        """Resolve keyword-only hits into citable passages."""
        del organization_id  # chunk ids are already tenant-scoped by the search that produced them
        passages: list[RetrievedPassage] = []
        for chunk_id in chunk_ids:
            chunk = await self._chunks.get_by_id(chunk_id)
            if chunk is None:
                continue
            document = await self._documents.get_by_id(chunk.document_id)
            if document is None:
                continue
            passages.append(
                RetrievedPassage(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    document_title=document.title,
                    document_uri=document.uri,
                    content=chunk.content,
                    score=1.0,
                )
            )
        return passages


def _from_similar(hit: SimilarChunk, score: float) -> RetrievedPassage:
    """Turn a vector hit into a citable passage carrying *score*."""
    return RetrievedPassage(
        chunk_id=hit.chunk_id,
        document_id=hit.document_id,
        document_title=hit.document_title,
        document_uri=hit.document_uri,
        content=hit.content,
        score=score,
    )


def _rescored(passage: RetrievedPassage, score: float) -> RetrievedPassage:
    """Return *passage* carrying its fused score instead of its own."""
    return RetrievedPassage(
        chunk_id=passage.chunk_id,
        document_id=passage.document_id,
        document_title=passage.document_title,
        document_uri=passage.document_uri,
        content=passage.content,
        score=score,
    )


__all__ = [
    "RRF_K",
    "IngestionResult",
    "RagPipeline",
    "RetrievedPassage",
    "content_hash",
]
