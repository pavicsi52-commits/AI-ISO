"""Repository for :class:`app.models.report_export.ReportExport`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ExportFormat
from app.models.report_export import ReportExport


class ReportExportRepository(BaseRepository[ReportExport]):
    """CRUD plus lookups for :class:`ReportExport`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ReportExport, tenant_scope=tenant_scope)

    async def list_for_execution(self, execution_id: UUID) -> list[ReportExport]:
        """Every artifact one execution produced."""
        stmt = self._base_select().where(ReportExport.execution_id == execution_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_execution_format(
        self, execution_id: UUID, export_format: ExportFormat
    ) -> ReportExport | None:
        """One execution's artifact in a specific format, if rendered."""
        stmt = self._base_select().where(
            ReportExport.execution_id == execution_id,
            ReportExport.export_format == export_format,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(self, organization_id: UUID, *, limit: int = 200) -> list[ReportExport]:
        """Artifacts for *organization_id*, most recent first."""
        stmt = (
            self._base_select()
            .where(ReportExport.organization_id == organization_id)
            .order_by(desc(ReportExport.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def record_download(self, export_id: UUID) -> ReportExport:
        """Increment an artifact's download counter.

        Raises:
            NotFoundError: If no such export exists.
        """
        export = await self.require_by_id(export_id)
        export.download_count += 1
        return await self.update(export)


__all__ = ["ReportExportRepository"]
