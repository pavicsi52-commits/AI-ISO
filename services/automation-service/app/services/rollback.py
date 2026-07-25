"""Roll an automation execution back.

Per docs/040 "ROLLBACK" "Support": Step Rollback, Execution Rollback,
Configuration Rollback, Playbook Rollback, Automatic Rollback, Manual
Rollback, Rollback Validation, Rollback Reports. ``initiate`` publishes
``RollbackStarted`` and leaves the rollback ``PENDING``; ``complete``
marks it done and publishes ``RollbackCompleted``. Applying the actual
inverse content (re-running a job's reverse playbook, or restoring a
prior :mod:`configuration-management-service` version) is out of this
service's scope -- it records and sequences the rollback operation
itself, matching the "Rollback Reports" framing rather than "Rollback
Execution".
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.automation_events import RollbackCompletedEvent, RollbackStartedEvent
from app.models.automation_rollback import AutomationRollback
from app.models.enums import RollbackStatus, RollbackType
from app.repositories.automation_execution import AutomationExecutionRepository
from app.repositories.automation_rollback import AutomationRollbackRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class AutomationRollbackService:
    """Initiates and completes automation execution rollbacks."""

    def __init__(
        self,
        rollbacks: AutomationRollbackRepository,
        executions: AutomationExecutionRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._rollbacks = rollbacks
        self._executions = executions
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, rollback_id: UUID) -> AutomationRollback:
        """Return the rollback identified by *rollback_id*.

        Raises:
            NotFoundError: If no such rollback exists.
        """
        return await self._rollbacks.require_by_id(rollback_id)

    async def list_for_execution(self, execution_id: UUID) -> list[AutomationRollback]:
        """Every rollback recorded for *execution_id*, newest first ("Rollback Reports")."""
        return await self._rollbacks.list_for_execution(execution_id)

    async def initiate(
        self,
        execution_id: UUID,
        *,
        rollback_type: RollbackType,
        initiated_by: UUID | None,
        reason: str | None,
    ) -> AutomationRollback:
        """Request a rollback of *execution_id* ("Manual Rollback"/"Automatic
        Rollback"), publishing ``RollbackStarted``.

        Raises:
            NotFoundError: If *execution_id* does not exist.
        """
        execution = await self._executions.require_by_id(execution_id)
        rollback = await self._rollbacks.create(
            AutomationRollback(
                organization_id=execution.organization_id,
                execution_id=execution_id,
                rollback_type=rollback_type,
                status=RollbackStatus.PENDING,
                initiated_by=initiated_by,
                reason=reason,
            )
        )
        await self._publish(
            RollbackStartedEvent(
                source_service="automation-service",
                payload={"rollback_id": str(rollback.id), "execution_id": str(execution_id)},
            )
        )
        return rollback

    async def complete(self, rollback_id: UUID, *, succeeded: bool) -> AutomationRollback:
        """Mark a rollback as finished ("Rollback Validation"), publishing
        ``RollbackCompleted`` on success.
        """
        rollback = await self.get_by_id(rollback_id)
        rollback.status = RollbackStatus.COMPLETED if succeeded else RollbackStatus.FAILED
        rollback.completed_at = datetime.now(UTC)
        rollback = await self._rollbacks.update(rollback)

        if succeeded:
            await self._publish(
                RollbackCompletedEvent(
                    source_service="automation-service",
                    payload={
                        "rollback_id": str(rollback.id),
                        "execution_id": str(rollback.execution_id),
                    },
                )
            )
        return rollback


__all__ = ["AutomationRollbackService"]
