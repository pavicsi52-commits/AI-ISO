"""Repository for :class:`app.models.graph_query.GraphQuery`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import QueryKind
from app.models.graph_query import GraphQuery


class GraphQueryRepository(BaseRepository[GraphQuery]):
    """CRUD plus lookups for :class:`GraphQuery`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, GraphQuery, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        kind: QueryKind | None = None,
        failed_only: bool = False,
        limit: int = 200,
    ) -> list[GraphQuery]:
        """Executed queries for one organization, most recent first."""
        stmt = self._base_select().where(GraphQuery.organization_id == organization_id)
        if kind is not None:
            stmt = stmt.where(GraphQuery.kind == kind)
        if failed_only:
            stmt = stmt.where(GraphQuery.succeeded.is_(False))
        stmt = stmt.order_by(desc(GraphQuery.executed_at)).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def slowest(self, organization_id: UUID, *, limit: int = 10) -> list[GraphQuery]:
        """The slowest recorded queries.

        Ordered in SQL rather than by sorting a loaded list: the whole
        point is to avoid materialising a large history to find ten rows.
        """
        stmt = (
            self._base_select()
            .where(
                GraphQuery.organization_id == organization_id,
                GraphQuery.duration_ms.is_not(None),
            )
            .order_by(desc(GraphQuery.duration_ms))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_org(self, organization_id: UUID) -> int:
        """How many queries an organization has run, counted in SQL."""
        stmt = (
            self._base_select()
            .with_only_columns(func.count(GraphQuery.id))
            .where(GraphQuery.organization_id == organization_id)
        )
        result = await self._session.execute(stmt)
        return int(result.scalar_one_or_none() or 0)


__all__ = ["GraphQueryRepository"]
