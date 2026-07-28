"""Repository for :class:`app.models.ai_session.AiSession`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_session import AiSession


class AiSessionRepository(BaseRepository[AiSession]):
    """CRUD plus lookup for :class:`AiSession`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AiSession, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[AiSession]:
        """Every row belonging to *organization_id*."""
        stmt = self._base_select().where(AiSession.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_open_for_user(self, organization_id: UUID, user_id: UUID) -> list[AiSession]:
        """Every still-open session for one user."""
        stmt = self._base_select().where(
            AiSession.organization_id == organization_id,
            AiSession.user_id == user_id,
            AiSession.is_open.is_(True),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AiSessionRepository"]
