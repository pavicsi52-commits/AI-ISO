"""Repository for :class:`app.models.monitoring_audit.MonitoringAuditEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring_audit import MonitoringAuditEntry


class MonitoringAuditEntryRepository(BaseRepository[MonitoringAuditEntry]):
    """CRUD plus lookup for :class:`MonitoringAuditEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MonitoringAuditEntry, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringAuditEntry]:
        """Every audit entry recorded for *organization_id*."""
        stmt = self._base_select().where(MonitoringAuditEntry.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["MonitoringAuditEntryRepository"]
