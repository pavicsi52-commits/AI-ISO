"""``plugin_health`` repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health import PluginHealth


class PluginHealthRepository(BaseRepository[PluginHealth]):
    """Automated health-probe results for installed plugin instances."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PluginHealth, tenant_scope=tenant_scope)

    async def list_for_installation(
        self, plugin_installation_id: UUID, *, limit: int = 100
    ) -> list[PluginHealth]:
        """One installation's own probe history, newest first."""
        stmt = (
            self._base_select()
            .where(PluginHealth.plugin_installation_id == plugin_installation_id)
            .order_by(PluginHealth.checked_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest(self, plugin_installation_id: UUID) -> PluginHealth | None:
        """One installation's own most recent probe result, if any."""
        stmt = (
            self._base_select()
            .where(PluginHealth.plugin_installation_id == plugin_installation_id)
            .order_by(PluginHealth.checked_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["PluginHealthRepository"]
