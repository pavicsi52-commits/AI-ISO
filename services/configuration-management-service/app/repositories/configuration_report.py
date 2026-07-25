"""Repository for :class:`app.models.configuration_report.ConfigurationReport`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration_report import ConfigurationReport
from app.models.enums import ConfigReportType


class ConfigurationReportRepository(BaseRepository[ConfigurationReport]):
    """CRUD plus lookup for :class:`ConfigurationReport`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConfigurationReport, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, report_type: ConfigReportType | None = None
    ) -> list[ConfigurationReport]:
        """Every generated report for *organization_id*, newest first,
        optionally narrowed to a single *report_type*.
        """
        stmt = self._base_select().where(ConfigurationReport.organization_id == organization_id)
        if report_type is not None:
            stmt = stmt.where(ConfigurationReport.report_type == report_type)
        stmt = stmt.order_by(desc(ConfigurationReport.generated_at))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationReport]:
        """Every generated report scoped to *profile_id*, newest first."""
        stmt = (
            self._base_select()
            .where(ConfigurationReport.profile_id == profile_id)
            .order_by(desc(ConfigurationReport.generated_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConfigurationReportRepository"]
