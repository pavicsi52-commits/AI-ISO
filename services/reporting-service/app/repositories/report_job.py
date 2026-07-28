"""Repository for :class:`app.models.report_job.ReportJob`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReportCategory
from app.models.report_job import ReportJob


class ReportJobRepository(BaseRepository[ReportJob]):
    """CRUD plus lookups for :class:`ReportJob`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ReportJob, tenant_scope=tenant_scope)

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        category: ReportCategory | None = None,
        enabled_only: bool = False,
    ) -> list[ReportJob]:
        """Reports for *organization_id*, optionally filtered."""
        stmt = self._base_select().where(ReportJob.organization_id == organization_id)
        if category is not None:
            stmt = stmt.where(ReportJob.category == category)
        if enabled_only:
            stmt = stmt.where(ReportJob.enabled.is_(True))
        stmt = stmt.order_by(ReportJob.name)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_owner(self, organization_id: UUID, owner_id: UUID) -> list[ReportJob]:
        """Reports owned by one user."""
        stmt = (
            self._base_select()
            .where(
                ReportJob.organization_id == organization_id,
                ReportJob.owner_id == owner_id,
            )
            .order_by(ReportJob.name)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ReportJobRepository"]
