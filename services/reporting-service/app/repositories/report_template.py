"""Repository for :class:`app.models.report_template.ReportTemplate`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReportCategory, TemplateStatus
from app.models.report_template import ReportTemplate


class ReportTemplateRepository(BaseRepository[ReportTemplate]):
    """CRUD plus lookups for :class:`ReportTemplate`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ReportTemplate, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, category: ReportCategory | None = None
    ) -> list[ReportTemplate]:
        """Every template for *organization_id*, newest version first."""
        stmt = self._base_select().where(ReportTemplate.organization_id == organization_id)
        if category is not None:
            stmt = stmt.where(ReportTemplate.category == category)
        stmt = stmt.order_by(ReportTemplate.name, desc(ReportTemplate.version_number))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_versions(self, organization_id: UUID, name: str) -> list[ReportTemplate]:
        """Every version of one named template, oldest first."""
        stmt = (
            self._base_select()
            .where(
                ReportTemplate.organization_id == organization_id,
                ReportTemplate.name == name,
            )
            .order_by(ReportTemplate.version_number)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_version(
        self, organization_id: UUID, name: str, version_number: str
    ) -> ReportTemplate | None:
        """Return one specific version of a named template."""
        stmt = self._base_select().where(
            ReportTemplate.organization_id == organization_id,
            ReportTemplate.name == name,
            ReportTemplate.version_number == version_number,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_latest_approved(self, organization_id: UUID, name: str) -> ReportTemplate | None:
        """The newest *approved* version of a named template.

        Report generation resolves templates through this, never
        through "the newest row": running an unreviewed draft against
        production data is exactly what the approval gate prevents.
        """
        stmt = (
            self._base_select()
            .where(
                ReportTemplate.organization_id == organization_id,
                ReportTemplate.name == name,
                ReportTemplate.status == TemplateStatus.APPROVED,
            )
            .order_by(desc(ReportTemplate.version_number))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["ReportTemplateRepository"]
