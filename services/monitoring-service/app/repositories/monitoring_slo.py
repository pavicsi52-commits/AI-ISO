"""Repository for :class:`app.models.monitoring_slo.MonitoringSLO`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring_slo import MonitoringSLO


class MonitoringSLORepository(BaseRepository[MonitoringSLO]):
    """CRUD plus lookup for :class:`MonitoringSLO`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MonitoringSLO, tenant_scope=tenant_scope)

    async def list_for_target(self, target_id: UUID) -> list[MonitoringSLO]:
        """Every SLO tracked for *target_id*."""
        stmt = self._base_select().where(MonitoringSLO.target_id == target_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringSLO]:
        """Every SLO belonging to *organization_id*."""
        stmt = self._base_select().where(MonitoringSLO.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["MonitoringSLORepository"]
