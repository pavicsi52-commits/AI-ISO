"""Repository for :class:`app.models.discovery_profile.DiscoveryProfile`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_profile import DiscoveryProfile


class DiscoveryProfileRepository(BaseRepository[DiscoveryProfile]):
    """CRUD plus lookup for :class:`DiscoveryProfile`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DiscoveryProfile, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[DiscoveryProfile]:
        """Every profile defined for *organization_id*."""
        stmt = self._base_select().where(DiscoveryProfile.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(self, organization_id: UUID, name: str) -> DiscoveryProfile | None:
        """Return the profile identified by *name* within *organization_id*, or ``None``."""
        stmt = self._base_select().where(
            DiscoveryProfile.organization_id == organization_id, DiscoveryProfile.name == name
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["DiscoveryProfileRepository"]
