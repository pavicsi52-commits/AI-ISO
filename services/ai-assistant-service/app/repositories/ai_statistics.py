"""Repository for :class:`app.models.ai_statistics.AiStatistics`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_statistics import AiStatistics


class AiStatisticsRepository(BaseRepository[AiStatistics]):
    """CRUD plus lookup for :class:`AiStatistics`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AiStatistics, tenant_scope=tenant_scope)

    async def get_for_org(self, organization_id: UUID) -> AiStatistics | None:
        """Return *organization_id*'s cached snapshot, or ``None``."""
        stmt = self._base_select().where(AiStatistics.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["AiStatisticsRepository"]
