"""Repository for :class:`app.models.monitoring_sla.MonitoringSLA`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring_sla import MonitoringSLA


class MonitoringSLARepository(BaseRepository[MonitoringSLA]):
    """CRUD plus lookup for :class:`MonitoringSLA`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MonitoringSLA, tenant_scope=tenant_scope)

    async def list_for_target(self, target_id: UUID) -> list[MonitoringSLA]:
        """Every SLA tracked for *target_id*."""
        stmt = self._base_select().where(MonitoringSLA.target_id == target_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringSLA]:
        """Every SLA belonging to *organization_id*."""
        stmt = self._base_select().where(MonitoringSLA.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["MonitoringSLARepository"]
