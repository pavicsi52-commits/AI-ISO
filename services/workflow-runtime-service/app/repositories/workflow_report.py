"""Repository for :class:`app.models.workflow_report.WorkflowReport`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WorkflowReportType
from app.models.workflow_report import WorkflowReport


class WorkflowReportRepository(BaseRepository[WorkflowReport]):
    """CRUD plus lookup for :class:`WorkflowReport`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WorkflowReport, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, report_type: WorkflowReportType | None = None
    ) -> list[WorkflowReport]:
        """Every generated report for *organization_id*, newest first,
        optionally narrowed to a single *report_type*.
        """
        stmt = self._base_select().where(WorkflowReport.organization_id == organization_id)
        if report_type is not None:
            stmt = stmt.where(WorkflowReport.report_type == report_type)
        stmt = stmt.order_by(desc(WorkflowReport.generated_at))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_instance(self, instance_id: UUID) -> list[WorkflowReport]:
        """Every generated report scoped to *instance_id*, newest first."""
        stmt = (
            self._base_select()
            .where(WorkflowReport.instance_id == instance_id)
            .order_by(desc(WorkflowReport.generated_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WorkflowReportRepository"]
