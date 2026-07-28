"""Repository for :class:`app.models.dashboard_audit.DashboardAudit`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard_audit import DashboardAudit
from app.models.enums import AuditAction


class DashboardAuditRepository(BaseRepository[DashboardAudit]):
    """Append-only writes plus lookups for :class:`DashboardAudit`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, DashboardAudit, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        action: AuditAction | None = None,
        limit: int = 200,
    ) -> list[DashboardAudit]:
        """Audit entries for *organization_id*, most recent first."""
        stmt = self._base_select().where(DashboardAudit.organization_id == organization_id)
        if action is not None:
            stmt = stmt.where(DashboardAudit.action == action)
        stmt = stmt.order_by(desc(DashboardAudit.occurred_at)).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_entity(self, entity_id: UUID, *, limit: int = 100) -> list[DashboardAudit]:
        """Everything audited against one entity, most recent first."""
        stmt = (
            self._base_select()
            .where(DashboardAudit.entity_id == entity_id)
            .order_by(desc(DashboardAudit.occurred_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["DashboardAuditRepository"]
