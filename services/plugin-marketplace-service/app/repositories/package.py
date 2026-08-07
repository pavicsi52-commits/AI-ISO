"""``plugin_packages`` repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.package import PluginPackage


class PluginPackageRepository(BaseRepository[PluginPackage]):
    """One version's own packaged, signed artifact."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PluginPackage, tenant_scope=tenant_scope)

    async def get_for_version(self, plugin_version_id: UUID) -> PluginPackage | None:
        """The package for one specific plugin version, if any."""
        stmt = self._base_select().where(PluginPackage.plugin_version_id == plugin_version_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_by_checksum(self, checksum: str) -> PluginPackage | None:
        """One package by its own content checksum, for dedupe/verification lookups."""
        stmt = self._base_select().where(PluginPackage.checksum == checksum)
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["PluginPackageRepository"]
