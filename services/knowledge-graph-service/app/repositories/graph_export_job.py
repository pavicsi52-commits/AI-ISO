"""Repository for :class:`app.models.graph_export_job.GraphExportJob`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.graph_export_job import GraphExportJob


class GraphExportJobRepository(BaseRepository[GraphExportJob]):
    """CRUD plus lookups for :class:`GraphExportJob`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, GraphExportJob, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, limit: int = 100
    ) -> list[GraphExportJob]:
        """Export runs for one organization, newest first."""
        stmt = (
            self._base_select()
            .where(GraphExportJob.organization_id == organization_id)
            .order_by(desc(GraphExportJob.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["GraphExportJobRepository"]
