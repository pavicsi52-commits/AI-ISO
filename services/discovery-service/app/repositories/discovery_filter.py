"""Repository for :class:`app.models.discovery_filter.DiscoveryFilter`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_filter import DiscoveryFilter


class DiscoveryFilterRepository(BaseRepository[DiscoveryFilter]):
    """CRUD plus lookup for :class:`DiscoveryFilter`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DiscoveryFilter, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[DiscoveryFilter]:
        """Every active filter defined for *organization_id*."""
        stmt = self._base_select().where(
            DiscoveryFilter.organization_id == organization_id, DiscoveryFilter.is_active.is_(True)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["DiscoveryFilterRepository"]
