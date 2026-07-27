"""Per docs/042 "TIMERS" "Support": Delay, Wait, Cron, Timeout,
Scheduled Resume, Recurring Timers, Event Timeout. ``DELAY``/``TIMER``
node types are handled entirely structurally by the SDK's own executor
(``asyncio.sleep``) and need no row here -- this service only tracks
the process-surviving cases: ``CRON``/``RECURRING`` workflow-level
schedules (wired into ``shared_core.scheduler`` by
``app/scheduling/registrar.py``) and ``EVENT_TIMEOUT`` watchdogs.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import TimerType
from app.models.workflow_timer import WorkflowTimer
from app.repositories.workflow_timer import WorkflowTimerRepository


class WorkflowTimerService:
    """Creates, reads, and fires workflow timers."""

    def __init__(self, timers: WorkflowTimerRepository) -> None:
        self._timers = timers

    async def create(
        self,
        *,
        organization_id: UUID,
        definition_id: UUID,
        timer_type: TimerType,
        instance_id: UUID | None = None,
        node_id: str | None = None,
        cron_expression: str | None = None,
        fires_at: datetime | None = None,
        recurring: bool = False,
    ) -> WorkflowTimer:
        """Declare a new timer for a workflow definition or instance."""
        return await self._timers.create(
            WorkflowTimer(
                organization_id=organization_id,
                definition_id=definition_id,
                instance_id=instance_id,
                node_id=node_id,
                timer_type=timer_type,
                cron_expression=cron_expression,
                fires_at=fires_at,
                recurring=recurring,
            )
        )

    async def list_for_definition(self, definition_id: UUID) -> list[WorkflowTimer]:
        """Every timer declared for *definition_id*."""
        return await self._timers.list_for_definition(definition_id)

    async def list_all_schedulable(self) -> list[WorkflowTimer]:
        """Every ``CRON``/``RECURRING`` timer with a ``cron_expression``,
        across every organization -- used once at process startup.
        """
        return await self._timers.list_all_schedulable()

    async def list_due(self, *, before: datetime) -> list[WorkflowTimer]:
        """Every not-yet-fired, non-recurring timer whose ``fires_at`` has passed."""
        return await self._timers.list_due(before=before)

    async def mark_fired(self, timer_id: UUID) -> WorkflowTimer:
        """Mark a one-shot timer as fired so it is never dispatched twice.

        Raises:
            NotFoundError: If no such timer exists.
        """
        timer = await self._timers.get_by_id(timer_id)
        if timer is None:
            raise NotFoundError(f"Workflow timer {timer_id!r} was not found.")
        timer.fired = True
        return await self._timers.update(timer)


__all__ = ["WorkflowTimerService"]
