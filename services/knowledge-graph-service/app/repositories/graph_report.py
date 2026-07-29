"""Repository for :class:`app.models.graph_report.GraphReport`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import QueryKind
from app.models.graph_report import GraphReport


class GraphReportRepository(BaseRepository[GraphReport]):
    """CRUD plus lookups for :class:`GraphReport`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, GraphReport, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        kind: QueryKind | None = None,
        limit: int = 100,
    ) -> list[GraphReport]:
        """Stored analyses for one organization, newest first."""
        stmt = self._base_select().where(GraphReport.organization_id == organization_id)
        if kind is not None:
            stmt = stmt.where(GraphReport.kind == kind)
        stmt = stmt.order_by(desc(GraphReport.generated_at)).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_root(self, root_key: str, *, limit: int = 50) -> list[GraphReport]:
        """Analyses rooted at one node, newest first."""
        stmt = (
            self._base_select()
            .where(GraphReport.root_key == root_key)
            .order_by(desc(GraphReport.generated_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["GraphReportRepository"]
