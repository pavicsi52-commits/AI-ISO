"""Repository for :class:`app.models.ai_retrieval_history.AiRetrievalHistory`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_retrieval_history import AiRetrievalHistory


class AiRetrievalHistoryRepository(BaseRepository[AiRetrievalHistory]):
    """CRUD plus lookup for :class:`AiRetrievalHistory`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AiRetrievalHistory, tenant_scope=tenant_scope)

    async def list_for_conversation(self, conversation_id: UUID) -> list[AiRetrievalHistory]:
        """Every retrieval performed within one conversation."""
        stmt = self._base_select().where(AiRetrievalHistory.conversation_id == conversation_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AiRetrievalHistoryRepository"]
