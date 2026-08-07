"""``plugin_dependencies`` repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dependency import PluginDependency


class PluginDependencyRepository(BaseRepository[PluginDependency]):
    """Dependency edges between plugins."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PluginDependency, tenant_scope=tenant_scope)

    async def list_for_plugin(self, plugin_id: UUID) -> list[PluginDependency]:
        """Every dependency declared by one plugin."""
        stmt = self._base_select().where(PluginDependency.plugin_id == plugin_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_dependents(self, plugin_id: UUID) -> list[PluginDependency]:
        """Every plugin that declares a dependency on *plugin_id*."""
        stmt = self._base_select().where(PluginDependency.depends_on_plugin_id == plugin_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_edges(self, organization_id: UUID) -> list[PluginDependency]:
        """Every dependency edge in this organization, for graph-wide cycle checks."""
        stmt = self._base_select().where(PluginDependency.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PluginDependencyRepository"]
