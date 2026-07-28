"""Repository for :class:`app.models.alert_oncall_schedule.AlertOnCallSchedule`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_oncall_schedule import AlertOnCallSchedule


class AlertOnCallScheduleRepository(BaseRepository[AlertOnCallSchedule]):
    """CRUD plus lookup for :class:`AlertOnCallSchedule`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AlertOnCallSchedule, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[AlertOnCallSchedule]:
        """Every on-call schedule belonging to *organization_id*."""
        stmt = self._base_select().where(AlertOnCallSchedule.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AlertOnCallScheduleRepository"]
