"""``plugin_upgrades`` and ``plugin_rollbacks`` repositories."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.upgrade import PluginRollback, PluginUpgrade


class PluginUpgradeRepository(BaseRepository[PluginUpgrade]):
    """One installation's own upgrade attempt history."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PluginUpgrade, tenant_scope=tenant_scope)

    async def list_for_installation(self, plugin_installation_id: UUID) -> list[PluginUpgrade]:
        """Every upgrade attempt for one installation, newest first."""
        stmt = (
            self._base_select()
            .where(PluginUpgrade.plugin_installation_id == plugin_installation_id)
            .order_by(PluginUpgrade.started_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class PluginRollbackRepository(BaseRepository[PluginRollback]):
    """One installation's own rollback attempt history."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PluginRollback, tenant_scope=tenant_scope)

    async def list_for_installation(self, plugin_installation_id: UUID) -> list[PluginRollback]:
        """Every rollback attempt for one installation, newest first."""
        stmt = (
            self._base_select()
            .where(PluginRollback.plugin_installation_id == plugin_installation_id)
            .order_by(PluginRollback.started_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PluginRollbackRepository", "PluginUpgradeRepository"]
