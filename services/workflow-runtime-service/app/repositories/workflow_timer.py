"""Repository for :class:`app.models.workflow_timer.WorkflowTimer`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import TimerType
from app.models.workflow_timer import WorkflowTimer


class WorkflowTimerRepository(BaseRepository[WorkflowTimer]):
    """CRUD plus lookup for :class:`WorkflowTimer`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WorkflowTimer, tenant_scope=tenant_scope)

    async def list_for_definition(self, definition_id: UUID) -> list[WorkflowTimer]:
        """Every timer declared for *definition_id*."""
        stmt = self._base_select().where(WorkflowTimer.definition_id == definition_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_schedulable(self) -> list[WorkflowTimer]:
        """Every ``CRON``/``RECURRING`` timer with a ``cron_expression``,
        across every organization -- used once at process startup to
        register this process's own :class:`~shared_core.scheduler.SchedulerManager`
        ("Cron"/"Recurring Timers"), the same system-wide bootstrap scan
        ``services/discovery-service``'s own ``list_active()`` established.
        """
        stmt = self._base_select().where(
            WorkflowTimer.timer_type.in_([TimerType.CRON, TimerType.RECURRING]),
            WorkflowTimer.cron_expression.is_not(None),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_due(self, *, before: datetime) -> list[WorkflowTimer]:
        """Every not-yet-fired, non-recurring timer whose ``fires_at`` has passed."""
        stmt = self._base_select().where(
            WorkflowTimer.fired.is_(False),
            WorkflowTimer.fires_at.is_not(None),
            WorkflowTimer.fires_at <= before,
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WorkflowTimerRepository"]
