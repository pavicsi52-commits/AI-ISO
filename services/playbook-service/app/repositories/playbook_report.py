"""Repository for :class:`app.models.playbook_report.PlaybookReport`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PlaybookReportType
from app.models.playbook_report import PlaybookReport


class PlaybookReportRepository(BaseRepository[PlaybookReport]):
    """CRUD plus lookup for :class:`PlaybookReport`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PlaybookReport, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, report_type: PlaybookReportType | None = None
    ) -> list[PlaybookReport]:
        """Every generated report for *organization_id*, newest first,
        optionally narrowed to a single *report_type*.
        """
        stmt = self._base_select().where(PlaybookReport.organization_id == organization_id)
        if report_type is not None:
            stmt = stmt.where(PlaybookReport.report_type == report_type)
        stmt = stmt.order_by(desc(PlaybookReport.generated_at))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookReport]:
        """Every generated report scoped to *playbook_id*, newest first."""
        stmt = (
            self._base_select()
            .where(PlaybookReport.playbook_id == playbook_id)
            .order_by(desc(PlaybookReport.generated_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["PlaybookReportRepository"]
