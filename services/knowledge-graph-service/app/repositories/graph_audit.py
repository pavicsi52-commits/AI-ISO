"""Repository for :class:`app.models.graph_audit.GraphAudit`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AuditAction
from app.models.graph_audit import GraphAudit


class GraphAuditRepository(BaseRepository[GraphAudit]):
    """Append-only writes plus lookups for :class:`GraphAudit`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, GraphAudit, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        action: AuditAction | None = None,
        limit: int = 200,
    ) -> list[GraphAudit]:
        """Audit entries for one organization, most recent first."""
        stmt = self._base_select().where(GraphAudit.organization_id == organization_id)
        if action is not None:
            stmt = stmt.where(GraphAudit.action == action)
        stmt = stmt.order_by(desc(GraphAudit.occurred_at)).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_entity(
        self, organization_id: UUID, entity_key: str, *, limit: int = 100
    ) -> list[GraphAudit]:
        """Everything audited against one entity, most recent first.

        Scoped to the organization like every other read here. A key
        is a business identifier -- "app-1", "host-1" -- so an
        unscoped lookup lets any tenant read another's rows by
        guessing one.
        """
        stmt = (
            self._base_select()
            .where(GraphAudit.organization_id == organization_id)
            .where(GraphAudit.entity_key == entity_key)
            .order_by(desc(GraphAudit.occurred_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["GraphAuditRepository"]
