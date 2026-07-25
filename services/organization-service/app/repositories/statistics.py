"""Repository for :class:`app.models.statistics.OrganizationStatistics`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.statistics import OrganizationStatistics


class OrganizationStatisticsRepository(BaseRepository[OrganizationStatistics]):
    """CRUD plus lookup for :class:`OrganizationStatistics`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, OrganizationStatistics, tenant_scope=tenant_scope)

    async def get_for_org(self, organization_id: UUID) -> OrganizationStatistics | None:
        """Return *organization_id*'s last-computed statistics row, or ``None``."""
        stmt = self._base_select().where(OrganizationStatistics.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["OrganizationStatisticsRepository"]
