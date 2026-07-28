"""Repository for :class:`app.models.report_statistics.ReportStatistics`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_statistics import ReportStatistics


class ReportStatisticsRepository(BaseRepository[ReportStatistics]):
    """CRUD plus lookup for :class:`ReportStatistics`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ReportStatistics, tenant_scope=tenant_scope)

    async def get_for_org(self, organization_id: UUID) -> ReportStatistics | None:
        """Return *organization_id*'s cached rollup, or ``None``."""
        stmt = self._base_select().where(ReportStatistics.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["ReportStatisticsRepository"]
