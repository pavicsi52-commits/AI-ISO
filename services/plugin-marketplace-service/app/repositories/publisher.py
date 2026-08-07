"""``plugin_publishers`` repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.publisher import PluginPublisher


class PluginPublisherRepository(BaseRepository[PluginPublisher]):
    """First-class publisher profiles."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PluginPublisher, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, publisher_id: UUID) -> PluginPublisher:
        """One publisher by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(PluginPublisher.organization_id == organization_id)
            .where(PluginPublisher.id == publisher_id)
        )
        result = await self._session.execute(stmt)
        found: PluginPublisher | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No publisher with id {publisher_id} in this organization.")
        return found

    async def get_by_slug(self, organization_id: UUID, slug: str) -> PluginPublisher | None:
        """One publisher by its own slug, if registered in this organization."""
        stmt = (
            self._base_select()
            .where(PluginPublisher.organization_id == organization_id)
            .where(PluginPublisher.slug == slug)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(self, organization_id: UUID) -> list[PluginPublisher]:
        """Every publisher profile registered in this organization."""
        stmt = self._base_select().where(PluginPublisher.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PluginPublisherRepository"]
