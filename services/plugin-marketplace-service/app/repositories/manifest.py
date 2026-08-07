"""``plugin_manifests`` repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.manifest import PluginManifestEntry


class PluginManifestRepository(BaseRepository[PluginManifestEntry]):
    """One version's own manifest content snapshot."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PluginManifestEntry, tenant_scope=tenant_scope)

    async def get_for_version(self, plugin_version_id: UUID) -> PluginManifestEntry | None:
        """The manifest snapshot for one specific plugin version, if any."""
        stmt = self._base_select().where(PluginManifestEntry.plugin_version_id == plugin_version_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_plugin(self, plugin_id: UUID) -> list[PluginManifestEntry]:
        """Every manifest snapshot across a plugin's own version history."""
        stmt = (
            self._base_select()
            .where(PluginManifestEntry.plugin_id == plugin_id)
            .order_by(PluginManifestEntry.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PluginManifestRepository"]
