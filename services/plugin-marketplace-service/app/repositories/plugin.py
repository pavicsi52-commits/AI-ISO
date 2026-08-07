"""``plugins`` and ``plugin_versions`` repositories."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PluginLifecycleStatus
from app.models.plugin import Plugin, PluginVersion


class PluginRepository(BaseRepository[Plugin]):
    """Organization-authored plugin definitions."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, Plugin, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, plugin_id: UUID) -> Plugin:
        """One plugin by id, scoped to its owning organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(Plugin.organization_id == organization_id)
            .where(Plugin.id == plugin_id)
        )
        result = await self._session.execute(stmt)
        found: Plugin | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No plugin with id {plugin_id} in this organization.")
        return found

    async def get_by_slug(self, organization_id: UUID, slug: str) -> Plugin | None:
        """One plugin by its own slug, if registered in this organization."""
        stmt = (
            self._base_select()
            .where(Plugin.organization_id == organization_id)
            .where(Plugin.slug == slug)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        category: str | None = None,
        status: PluginLifecycleStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Plugin]:
        """Plugins owned by this organization, newest first."""
        stmt = self._base_select().where(Plugin.organization_id == organization_id)
        if category is not None:
            stmt = stmt.where(Plugin.category == category)
        if status is not None:
            stmt = stmt.where(Plugin.status == str(status))
        stmt = stmt.order_by(Plugin.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_publisher(self, publisher_id: UUID) -> list[Plugin]:
        """Every plugin authored by one publisher, across organizations."""
        stmt = self._base_select().where(Plugin.publisher_id == publisher_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class PluginVersionRepository(BaseRepository[PluginVersion]):
    """A plugin's own published version history."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PluginVersion, tenant_scope=tenant_scope)

    async def list_for_plugin(self, plugin_id: UUID) -> list[PluginVersion]:
        """Every version of one plugin, newest first."""
        stmt = (
            self._base_select()
            .where(PluginVersion.plugin_id == plugin_id)
            .order_by(PluginVersion.released_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_current(self, plugin_id: UUID) -> PluginVersion | None:
        """The plugin's own currently-published version row, if any."""
        stmt = (
            self._base_select()
            .where(PluginVersion.plugin_id == plugin_id)
            .where(PluginVersion.is_current.is_(True))
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_by_version_number(
        self, plugin_id: UUID, version_number: str
    ) -> PluginVersion | None:
        """One specific version of one plugin, by its own version number."""
        stmt = (
            self._base_select()
            .where(PluginVersion.plugin_id == plugin_id)
            .where(PluginVersion.version_number == version_number)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["PluginRepository", "PluginVersionRepository"]
