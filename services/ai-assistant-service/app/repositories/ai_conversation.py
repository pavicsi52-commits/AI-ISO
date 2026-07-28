"""Repository for :class:`app.models.ai_conversation.AiConversation`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_conversation import AiConversation


class AiConversationRepository(BaseRepository[AiConversation]):
    """CRUD plus lookup for :class:`AiConversation`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AiConversation, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[AiConversation]:
        """Every row belonging to *organization_id*."""
        stmt = self._base_select().where(AiConversation.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_user(self, organization_id: UUID, user_id: UUID) -> list[AiConversation]:
        """Every conversation belonging to one user, most recent first."""
        stmt = (
            self._base_select()
            .where(
                AiConversation.organization_id == organization_id,
                AiConversation.user_id == user_id,
            )
            .order_by(AiConversation.started_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AiConversationRepository"]
