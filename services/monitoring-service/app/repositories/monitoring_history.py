"""Repository for :class:`app.models.monitoring_history.MonitoringHistory`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring_history import MonitoringHistory


class MonitoringHistoryRepository(BaseRepository[MonitoringHistory]):
    """CRUD plus lookup for :class:`MonitoringHistory`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MonitoringHistory, tenant_scope=tenant_scope)

    async def list_for_target(self, target_id: UUID) -> list[MonitoringHistory]:
        """Every historical snapshot for *target_id*, oldest first."""
        stmt = (
            self._base_select()
            .where(MonitoringHistory.target_id == target_id)
            .order_by(MonitoringHistory.recorded_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringHistory]:
        """Every historical snapshot for *organization_id*, oldest first."""
        stmt = (
            self._base_select()
            .where(MonitoringHistory.organization_id == organization_id)
            .order_by(MonitoringHistory.recorded_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["MonitoringHistoryRepository"]
