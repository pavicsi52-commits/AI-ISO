"""Repository for :class:`app.models.ai_report.AiReport`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_report import AiReport
from app.models.enums import AiReportType


class AiReportRepository(BaseRepository[AiReport]):
    """CRUD plus lookup for :class:`AiReport`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AiReport, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[AiReport]:
        """Every row belonging to *organization_id*."""
        stmt = self._base_select().where(AiReport.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_type(
        self, organization_id: UUID, report_type: AiReportType
    ) -> list[AiReport]:
        """Every report of one type for *organization_id*."""
        stmt = self._base_select().where(
            AiReport.organization_id == organization_id, AiReport.report_type == report_type
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AiReportRepository"]
