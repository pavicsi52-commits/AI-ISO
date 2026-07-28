"""Repository for :class:`app.models.alert_report.AlertReport`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_report import AlertReport
from app.models.enums import AlertReportType


class AlertReportRepository(BaseRepository[AlertReport]):
    """CRUD plus lookup for :class:`AlertReport`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AlertReport, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, report_type: AlertReportType | None = None
    ) -> list[AlertReport]:
        """Every report generated for *organization_id*, optionally filtered by type."""
        stmt = self._base_select().where(AlertReport.organization_id == organization_id)
        if report_type is not None:
            stmt = stmt.where(AlertReport.report_type == report_type)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AlertReportRepository"]
