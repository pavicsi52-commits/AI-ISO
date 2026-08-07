"""``plugin_installations`` repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PluginInstallationStatus
from app.models.installation import PluginInstallation


class PluginInstallationRepository(BaseRepository[PluginInstallation]):
    """One organization's own installed plugin instances."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PluginInstallation, tenant_scope=tenant_scope)

    async def require_in_org(
        self, organization_id: UUID, installation_id: UUID
    ) -> PluginInstallation:
        """One installation by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(PluginInstallation.organization_id == organization_id)
            .where(PluginInstallation.id == installation_id)
        )
        result = await self._session.execute(stmt)
        found: PluginInstallation | None = result.scalars().first()
        if found is None:
            raise NotFoundError(
                f"No plugin installation with id {installation_id} in this organization."
            )
        return found

    async def get_for_plugin(
        self, organization_id: UUID, plugin_id: UUID
    ) -> PluginInstallation | None:
        """This organization's own installation of one plugin, if any."""
        stmt = (
            self._base_select()
            .where(PluginInstallation.organization_id == organization_id)
            .where(PluginInstallation.plugin_id == plugin_id)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        status: PluginInstallationStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[PluginInstallation]:
        """This organization's own installations, newest first."""
        stmt = self._base_select().where(PluginInstallation.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(PluginInstallation.status == str(status))
        stmt = stmt.order_by(PluginInstallation.installed_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_for_plugin(self, plugin_id: UUID) -> list[PluginInstallation]:
        """Every active installation of one plugin, across every organization
        -- for the health-probe sweep.
        """
        stmt = (
            self._base_select()
            .where(PluginInstallation.plugin_id == plugin_id)
            .where(PluginInstallation.status == PluginInstallationStatus.ACTIVE)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_active(self, *, limit: int = 500) -> list[PluginInstallation]:
        """Every active installation across every organization -- for the health-probe sweep."""
        stmt = (
            self._base_select()
            .where(PluginInstallation.status == PluginInstallationStatus.ACTIVE)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PluginInstallationRepository"]
