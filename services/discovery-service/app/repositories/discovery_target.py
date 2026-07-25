"""Repository for :class:`app.models.discovery_target.DiscoveryTarget`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_target import DiscoveryTarget


class DiscoveryTargetRepository(BaseRepository[DiscoveryTarget]):
    """CRUD plus lookup for :class:`DiscoveryTarget`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DiscoveryTarget, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[DiscoveryTarget]:
        """Every target defined for *organization_id*."""
        stmt = self._base_select().where(DiscoveryTarget.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_profile(self, profile_id: UUID) -> list[DiscoveryTarget]:
        """Every active target associated with *profile_id*."""
        stmt = self._base_select().where(
            DiscoveryTarget.profile_id == profile_id, DiscoveryTarget.is_active.is_(True)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["DiscoveryTargetRepository"]
