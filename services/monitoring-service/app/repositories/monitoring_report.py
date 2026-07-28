"""Repository for :class:`app.models.monitoring_report.MonitoringReport`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MonitoringReportType
from app.models.monitoring_report import MonitoringReport


class MonitoringReportRepository(BaseRepository[MonitoringReport]):
    """CRUD plus lookup for :class:`MonitoringReport`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MonitoringReport, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, report_type: MonitoringReportType | None = None
    ) -> list[MonitoringReport]:
        """Every report generated for *organization_id*, optionally filtered by type."""
        stmt = self._base_select().where(MonitoringReport.organization_id == organization_id)
        if report_type is not None:
            stmt = stmt.where(MonitoringReport.report_type == report_type)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["MonitoringReportRepository"]
