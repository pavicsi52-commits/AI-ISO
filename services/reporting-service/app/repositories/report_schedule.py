"""Repository for :class:`app.models.report_schedule.ReportSchedule`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_schedule import ReportSchedule


class ReportScheduleRepository(BaseRepository[ReportSchedule]):
    """CRUD plus lookups for :class:`ReportSchedule`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ReportSchedule, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[ReportSchedule]:
        """Every schedule for *organization_id*."""
        stmt = self._base_select().where(ReportSchedule.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_job(self, job_id: UUID) -> list[ReportSchedule]:
        """Every schedule attached to one report."""
        stmt = self._base_select().where(ReportSchedule.job_id == job_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_due(self, moment: datetime, *, limit: int = 100) -> list[ReportSchedule]:
        """Enabled schedules whose next run has arrived.

        Filtering is pushed into SQL rather than done in Python: the
        worker polls this on every tick, and loading every schedule in
        the deployment to discard most of them would not survive
        contact with a real installation. Bounded by *limit* so one
        tick cannot pick up an unbounded backlog.
        """
        stmt = (
            self._base_select()
            .where(
                ReportSchedule.enabled.is_(True),
                ReportSchedule.next_run_at.is_not(None),
                ReportSchedule.next_run_at <= moment,
                ReportSchedule.starts_at <= moment,
                or_(ReportSchedule.ends_at.is_(None), ReportSchedule.ends_at >= moment),
            )
            .order_by(ReportSchedule.next_run_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ReportScheduleRepository"]
