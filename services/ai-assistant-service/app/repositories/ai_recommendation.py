"""Repository for :class:`app.models.ai_recommendation.AiRecommendation`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_recommendation import AiRecommendation


class AiRecommendationRepository(BaseRepository[AiRecommendation]):
    """CRUD plus lookup for :class:`AiRecommendation`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AiRecommendation, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[AiRecommendation]:
        """Every row belonging to *organization_id*."""
        stmt = self._base_select().where(AiRecommendation.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_conversation(self, conversation_id: UUID) -> list[AiRecommendation]:
        """Every recommendation generated within one conversation."""
        stmt = self._base_select().where(AiRecommendation.conversation_id == conversation_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AiRecommendationRepository"]
