"""Repository for :class:`app.models.automation_schedule.AutomationSchedule`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_schedule import AutomationSchedule


class AutomationScheduleRepository(BaseRepository[AutomationSchedule]):
    """CRUD plus lookup for :class:`AutomationSchedule`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AutomationSchedule, tenant_scope=tenant_scope)

    async def list_for_job(self, job_id: UUID) -> list[AutomationSchedule]:
        """Every schedule recorded for *job_id*."""
        stmt = self._base_select().where(AutomationSchedule.job_id == job_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_enabled_for_org(self, organization_id: UUID) -> list[AutomationSchedule]:
        """Every enabled schedule for *organization_id*."""
        stmt = self._base_select().where(
            AutomationSchedule.organization_id == organization_id,
            AutomationSchedule.enabled.is_(True),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AutomationScheduleRepository"]
