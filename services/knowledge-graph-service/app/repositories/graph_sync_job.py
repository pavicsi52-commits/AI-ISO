"""Repository for :class:`app.models.graph_sync_job.GraphSyncJob`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SyncSource, SyncStatus
from app.models.graph_sync_job import GraphSyncJob


class GraphSyncJobRepository(BaseRepository[GraphSyncJob]):
    """CRUD plus lookups for :class:`GraphSyncJob`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, GraphSyncJob, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        source: SyncSource | None = None,
        status: SyncStatus | None = None,
        limit: int = 100,
    ) -> list[GraphSyncJob]:
        """Sync runs for one organization, most recent first."""
        stmt = self._base_select().where(GraphSyncJob.organization_id == organization_id)
        if source is not None:
            stmt = stmt.where(GraphSyncJob.source == source)
        if status is not None:
            stmt = stmt.where(GraphSyncJob.status == status)
        stmt = stmt.order_by(desc(GraphSyncJob.created_at)).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def latest_for_source(
        self, organization_id: UUID, source: SyncSource
    ) -> GraphSyncJob | None:
        """The newest run against one source.

        This is what answers "when did inventory last sync, and did it
        work?" and what the engine reads to resume an incremental run
        from its cursor.
        """
        stmt = (
            self._base_select()
            .where(
                GraphSyncJob.organization_id == organization_id,
                GraphSyncJob.source == source,
            )
            .order_by(desc(GraphSyncJob.created_at))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_running(self, organization_id: UUID) -> list[GraphSyncJob]:
        """Runs currently in flight, so a second tick does not double-start one."""
        stmt = self._base_select().where(
            GraphSyncJob.organization_id == organization_id,
            GraphSyncJob.status == SyncStatus.RUNNING,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["GraphSyncJobRepository"]
