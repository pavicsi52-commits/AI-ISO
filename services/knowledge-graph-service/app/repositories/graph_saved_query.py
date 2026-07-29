"""Repository for :class:`app.models.graph_saved_query.GraphSavedQuery`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.graph_saved_query import GraphSavedQuery


class GraphSavedQueryRepository(BaseRepository[GraphSavedQuery]):
    """CRUD plus lookups for :class:`GraphSavedQuery`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, GraphSavedQuery, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[GraphSavedQuery]:
        """Saved queries for one organization, by name."""
        stmt = (
            self._base_select()
            .where(GraphSavedQuery.organization_id == organization_id)
            .order_by(GraphSavedQuery.name)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_slug(self, organization_id: UUID, slug: str) -> GraphSavedQuery | None:
        """Return the saved query registered under *slug*, if any."""
        stmt = self._base_select().where(
            GraphSavedQuery.organization_id == organization_id,
            GraphSavedQuery.slug == slug,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["GraphSavedQueryRepository"]
