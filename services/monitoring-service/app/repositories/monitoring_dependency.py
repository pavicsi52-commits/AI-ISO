"""Repository for :class:`app.models.monitoring_dependency.MonitoringDependency`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring_dependency import MonitoringDependency


class MonitoringDependencyRepository(BaseRepository[MonitoringDependency]):
    """CRUD plus lookup for :class:`MonitoringDependency`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MonitoringDependency, tenant_scope=tenant_scope)

    async def list_children(self, parent_target_id: UUID) -> list[MonitoringDependency]:
        """Every dependency edge where *parent_target_id* is depended upon
        ("Blast Radius Calculation").
        """
        stmt = self._base_select().where(MonitoringDependency.parent_target_id == parent_target_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_parents(self, child_target_id: UUID) -> list[MonitoringDependency]:
        """Every dependency edge where *child_target_id* is the dependent target."""
        stmt = self._base_select().where(MonitoringDependency.child_target_id == child_target_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["MonitoringDependencyRepository"]
