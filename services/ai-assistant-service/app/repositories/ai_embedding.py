"""Repository for :class:`app.models.ai_embedding.AiEmbedding`,
including the real pgvector nearest-neighbour search RAG depends on.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_chunk import AiChunk
from app.models.ai_document import AiDocument
from app.models.ai_embedding import AiEmbedding
from app.models.enums import DocumentSourceType


@dataclass(frozen=True, slots=True)
class SimilarChunk:
    """One vector-search hit, with everything a citation needs."""

    chunk_id: UUID
    document_id: UUID
    document_title: str
    document_uri: str | None
    content: str
    distance: float

    @property
    def similarity(self) -> float:
        """Cosine similarity in ``[0, 1]``, derived from cosine distance.

        pgvector's ``<=>`` returns *distance* (0 = identical); callers
        ranking or thresholding results almost always mean similarity,
        so both are exposed rather than leaving each caller to invert
        it and risk one getting the direction backwards.
        """
        return 1.0 - self.distance


class AiEmbeddingRepository(BaseRepository[AiEmbedding]):
    """CRUD plus real vector similarity search for :class:`AiEmbedding`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AiEmbedding, tenant_scope=tenant_scope)

    async def list_for_chunk(self, chunk_id: UUID) -> list[AiEmbedding]:
        """Every embedding generated for *chunk_id*.

        More than one can exist: re-embedding with a different model
        keeps the old vector until the re-index completes.
        """
        stmt = self._base_select().where(AiEmbedding.chunk_id == chunk_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def search_similar(
        self,
        organization_id: UUID,
        query_vector: list[float],
        *,
        top_k: int = 5,
        model: str | None = None,
        source_types: list[DocumentSourceType] | None = None,
    ) -> list[SimilarChunk]:
        """Nearest chunks to *query_vector* by real cosine distance.

        Uses pgvector's own ``<=>`` operator (``cosine_distance``) with
        the ordering and limit pushed into SQL, so the database returns
        only ``top_k`` rows rather than this process loading every
        embedding and sorting in Python.

        *model* filters to vectors produced by one embedder --
        important because distances between vectors from *different*
        models are meaningless, so mixing them would silently corrupt
        ranking. *source_types* backs "Metadata Filtering".
        """
        distance = AiEmbedding.vector.cosine_distance(query_vector)
        stmt = (
            select(
                AiChunk.id,
                AiDocument.id,
                AiDocument.title,
                AiDocument.uri,
                AiChunk.content,
                distance.label("distance"),
            )
            .join(AiChunk, AiChunk.id == AiEmbedding.chunk_id)
            .join(AiDocument, AiDocument.id == AiChunk.document_id)
            .where(AiEmbedding.organization_id == organization_id)
        )
        if model is not None:
            stmt = stmt.where(AiEmbedding.model == model)
        if source_types:
            stmt = stmt.where(AiDocument.source_type.in_(source_types))
        stmt = stmt.order_by(distance).limit(top_k)

        result = await self._session.execute(stmt)
        return [
            SimilarChunk(
                chunk_id=row[0],
                document_id=row[1],
                document_title=row[2],
                document_uri=row[3],
                content=row[4],
                distance=float(row[5]),
            )
            for row in result.all()
        ]

    async def delete_for_chunk(self, chunk_id: UUID) -> int:
        """Delete every embedding for *chunk_id*, returning the count.

        Used when re-embedding a changed chunk: the stale vector must
        go, or a search would rank against text that no longer exists.
        """
        rows = await self.list_for_chunk(chunk_id)
        for row in rows:
            await self._session.delete(row)
        await self._session.flush()
        return len(rows)


__all__ = ["AiEmbeddingRepository", "SimilarChunk"]
