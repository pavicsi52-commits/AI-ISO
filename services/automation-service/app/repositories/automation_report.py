"""Repository for :class:`app.models.automation_report.AutomationReport`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_report import AutomationReport
from app.models.enums import AutomationReportType


class AutomationReportRepository(BaseRepository[AutomationReport]):
    """CRUD plus lookup for :class:`AutomationReport`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AutomationReport, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, report_type: AutomationReportType | None = None
    ) -> list[AutomationReport]:
        """Every generated report for *organization_id*, newest first,
        optionally narrowed to a single *report_type*.
        """
        stmt = self._base_select().where(AutomationReport.organization_id == organization_id)
        if report_type is not None:
            stmt = stmt.where(AutomationReport.report_type == report_type)
        stmt = stmt.order_by(desc(AutomationReport.generated_at))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_job(self, job_id: UUID) -> list[AutomationReport]:
        """Every generated report scoped to *job_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AutomationReport.job_id == job_id)
            .order_by(desc(AutomationReport.generated_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AutomationReportRepository"]
