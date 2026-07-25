"""Repository for :class:`app.models.asset_report.AssetReport`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset_report import AssetReport
from app.models.enums import ReportType


class AssetReportRepository(BaseRepository[AssetReport]):
    """CRUD plus lookup for :class:`AssetReport`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AssetReport, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, report_type: ReportType | None = None
    ) -> list[AssetReport]:
        """Every generated report for *organization_id*, newest first,
        optionally narrowed to a single *report_type*.
        """
        stmt = self._base_select().where(AssetReport.organization_id == organization_id)
        if report_type is not None:
            stmt = stmt.where(AssetReport.report_type == report_type)
        stmt = stmt.order_by(desc(AssetReport.generated_at))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetReport]:
        """Every generated report scoped to *managed_asset_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AssetReport.managed_asset_id == managed_asset_id)
            .order_by(desc(AssetReport.generated_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AssetReportRepository"]
