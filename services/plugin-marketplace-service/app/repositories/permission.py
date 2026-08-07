"""``plugin_permissions`` repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PermissionGrantStatus, PluginPermissionCategory
from app.models.permission import PluginPermissionGrant


class PluginPermissionRepository(BaseRepository[PluginPermissionGrant]):
    """Capability grants for one installed plugin instance."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PluginPermissionGrant, tenant_scope=tenant_scope)

    async def list_for_installation(
        self, plugin_installation_id: UUID
    ) -> list[PluginPermissionGrant]:
        """Every capability grant requested for one installation."""
        stmt = self._base_select().where(
            PluginPermissionGrant.plugin_installation_id == plugin_installation_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_granted(self, plugin_installation_id: UUID) -> list[PluginPermissionGrant]:
        """Only the currently-granted capabilities for one installation."""
        stmt = (
            self._base_select()
            .where(PluginPermissionGrant.plugin_installation_id == plugin_installation_id)
            .where(PluginPermissionGrant.status == PermissionGrantStatus.GRANTED)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_category(
        self, plugin_installation_id: UUID, category: PluginPermissionCategory
    ) -> PluginPermissionGrant | None:
        """One installation's own grant row for a specific capability category, if any."""
        stmt = (
            self._base_select()
            .where(PluginPermissionGrant.plugin_installation_id == plugin_installation_id)
            .where(PluginPermissionGrant.category == category)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["PluginPermissionRepository"]
