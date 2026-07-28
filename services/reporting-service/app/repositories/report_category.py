"""Repository for :class:`app.models.report_category.ReportCategoryRecord`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_category import ReportCategoryRecord


class ReportCategoryRepository(BaseRepository[ReportCategoryRecord]):
    """CRUD plus lookups for :class:`ReportCategoryRecord`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ReportCategoryRecord, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[ReportCategoryRecord]:
        """Every category for *organization_id*, in display order."""
        stmt = (
            self._base_select()
            .where(ReportCategoryRecord.organization_id == organization_id)
            .order_by(ReportCategoryRecord.display_order, ReportCategoryRecord.name)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_slug(self, organization_id: UUID, slug: str) -> ReportCategoryRecord | None:
        """Return the category registered under *slug*, if any.

        Backs the unique constraint with a friendly pre-check so a
        duplicate returns a clear conflict instead of an integrity error.
        """
        stmt = self._base_select().where(
            ReportCategoryRecord.organization_id == organization_id,
            ReportCategoryRecord.slug == slug,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["ReportCategoryRepository"]
