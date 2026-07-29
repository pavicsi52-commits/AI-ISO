"""Repository for :class:`app.models.graph_change_history.GraphChangeHistory`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.graph_change_history import GraphChangeHistory


class GraphChangeHistoryRepository(BaseRepository[GraphChangeHistory]):
    """Append-only writes plus lookups for :class:`GraphChangeHistory`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, GraphChangeHistory, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        since: datetime | None = None,
        limit: int = 200,
    ) -> list[GraphChangeHistory]:
        """Changes for one organization, most recent first."""
        stmt = self._base_select().where(GraphChangeHistory.organization_id == organization_id)
        if since is not None:
            stmt = stmt.where(GraphChangeHistory.occurred_at >= since)
        stmt = stmt.order_by(desc(GraphChangeHistory.occurred_at)).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_node(self, node_key: str, *, limit: int = 100) -> list[GraphChangeHistory]:
        """Everything that has happened to one node, most recent first."""
        stmt = (
            self._base_select()
            .where(GraphChangeHistory.node_key == node_key)
            .order_by(desc(GraphChangeHistory.occurred_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_sync_job(self, sync_job_id: UUID) -> list[GraphChangeHistory]:
        """Everything one synchronization run changed.

        This is what makes a sync auditable: "what did last night run
        actually do to the graph?" is otherwise unanswerable.
        """
        stmt = (
            self._base_select()
            .where(GraphChangeHistory.sync_job_id == sync_job_id)
            .order_by(GraphChangeHistory.occurred_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["GraphChangeHistoryRepository"]
