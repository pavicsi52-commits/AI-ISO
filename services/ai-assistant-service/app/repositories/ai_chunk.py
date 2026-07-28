"""Repository for :class:`app.models.ai_chunk.AiChunk`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_chunk import AiChunk


class AiChunkRepository(BaseRepository[AiChunk]):
    """CRUD plus lookup for :class:`AiChunk`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AiChunk, tenant_scope=tenant_scope)

    async def list_for_document(self, document_id: UUID) -> list[AiChunk]:
        """Every chunk of a document, in order."""
        stmt = (
            self._base_select()
            .where(AiChunk.document_id == document_id)
            .order_by(AiChunk.sequence.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def search_keyword(
        self, organization_id: UUID, terms: list[str], *, limit: int = 20
    ) -> list[AiChunk]:
        """Chunks containing any of *terms* ("RAG": Hybrid Search).

        Case-insensitive ``ILIKE`` matching rather than a Postgres
        full-text index: this is the lexical half of hybrid search,
        whose job is to catch exact identifiers (a hostname, an error
        code) that a semantic vector often misses. Stemming would
        actively hurt that.
        """
        if not terms:
            return []
        stmt = (
            self._base_select()
            .where(
                AiChunk.organization_id == organization_id,
                or_(*(AiChunk.content.ilike(f"%{term}%") for term in terms)),
            )
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_for_document(self, document_id: UUID) -> int:
        """Delete every chunk of a document, returning the count."""
        rows = await self.list_for_document(document_id)
        for row in rows:
            await self._session.delete(row)
        await self._session.flush()
        return len(rows)


__all__ = ["AiChunkRepository"]
