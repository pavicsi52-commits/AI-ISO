"""Repository for :class:`app.models.monitoring_synthetic_test.MonitoringSyntheticTest`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring_synthetic_test import MonitoringSyntheticTest


class MonitoringSyntheticTestRepository(BaseRepository[MonitoringSyntheticTest]):
    """CRUD plus lookup for :class:`MonitoringSyntheticTest`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MonitoringSyntheticTest, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringSyntheticTest]:
        """Every synthetic test belonging to *organization_id*."""
        stmt = self._base_select().where(MonitoringSyntheticTest.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_active(self) -> list[MonitoringSyntheticTest]:
        """Every active synthetic test, system-wide (for scheduling)."""
        stmt = self._base_select().where(MonitoringSyntheticTest.is_active.is_(True))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["MonitoringSyntheticTestRepository"]
