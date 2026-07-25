"""Repository for :class:`app.models.inventory_statistics.InventoryStatistics`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_statistics import InventoryStatistics


class InventoryStatisticsRepository(BaseRepository[InventoryStatistics]):
    """CRUD plus lookup for :class:`InventoryStatistics`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, InventoryStatistics, tenant_scope=tenant_scope)

    async def get_for_org(self, organization_id: UUID) -> InventoryStatistics | None:
        """Return *organization_id*'s cached statistics snapshot, or ``None``."""
        stmt = self._base_select().where(InventoryStatistics.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["InventoryStatisticsRepository"]
