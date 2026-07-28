"""Repository for :class:`app.models.report_history.ReportHistory`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_history import ReportHistory


class ReportHistoryRepository(BaseRepository[ReportHistory]):
    """CRUD plus lookups for :class:`ReportHistory`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ReportHistory, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID, *, limit: int = 200) -> list[ReportHistory]:
        """Activity for *organization_id*, most recent first."""
        stmt = (
            self._base_select()
            .where(ReportHistory.organization_id == organization_id)
            .order_by(desc(ReportHistory.occurred_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_job(self, job_id: UUID, *, limit: int = 100) -> list[ReportHistory]:
        """Activity on one report, most recent first."""
        stmt = (
            self._base_select()
            .where(ReportHistory.job_id == job_id)
            .order_by(desc(ReportHistory.occurred_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ReportHistoryRepository"]
