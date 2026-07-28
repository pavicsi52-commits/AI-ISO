"""Repository for :class:`app.models.ai_document.AiDocument`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_document import AiDocument
from app.models.enums import DocumentSourceType


class AiDocumentRepository(BaseRepository[AiDocument]):
    """CRUD plus lookup for :class:`AiDocument`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AiDocument, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[AiDocument]:
        """Every row belonging to *organization_id*."""
        stmt = self._base_select().where(AiDocument.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_content_hash(
        self, organization_id: UUID, content_hash: str
    ) -> AiDocument | None:
        """Return an already-ingested document with this exact content.

        Backs "Incremental Indexing": an unchanged document is detected
        here and skipped rather than re-chunked and re-embedded.
        """
        stmt = self._base_select().where(
            AiDocument.organization_id == organization_id,
            AiDocument.content_hash == content_hash,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_by_external_id(
        self, organization_id: UUID, source_type: DocumentSourceType, external_id: str
    ) -> AiDocument | None:
        """Return the document already ingested for this source record."""
        stmt = self._base_select().where(
            AiDocument.organization_id == organization_id,
            AiDocument.source_type == source_type,
            AiDocument.external_id == external_id,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["AiDocumentRepository"]
