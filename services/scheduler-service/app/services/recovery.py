"""Manual recovery of a terminal (retries-exhausted) failure."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.logging.logger import get_logger

from app.events.scheduler_events import SOURCE_SERVICE, SchedulerRecoveredEvent
from app.models.enums import RecoveryAction
from app.models.history import JobFailure
from app.notifications.scheduler_notifications import SchedulerNotificationService
from app.repositories.history import JobFailureRepository
from app.repositories.job import ScheduledJobRepository
from app.services.execution import ExecutionService
from app.types import EventPublisher

logger = get_logger("app.services.recovery")

_REDISPATCHING_ACTIONS = frozenset(
    {
        RecoveryAction.AUTOMATIC_RETRY,
        RecoveryAction.RESUME_EXECUTION,
        RecoveryAction.RESTART_EXECUTION,
    }
)
"""Which recovery actions actually dispatch a fresh execution attempt.
``CHECKPOINT_RECOVERY``, ``ROLLBACK_TRIGGER``, and ``MANUAL_RECOVERY``
record that a human or an external process handled it some other way --
this service has no checkpoint or rollback mechanism of its own to
invoke for them, consistent with never performing a job's own work."""


class RecoveryService:
    """Recovers a terminal failure, optionally dispatching a fresh attempt."""

    def __init__(
        self,
        failures: JobFailureRepository,
        jobs: ScheduledJobRepository,
        executions: ExecutionService,
        notifications: SchedulerNotificationService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._failures = failures
        self._jobs = jobs
        self._executions = executions
        self._notifications = notifications
        self._publish = publish_event

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def recover(
        self,
        organization_id: UUID,
        failure_id: UUID,
        *,
        action: RecoveryAction,
        recovered_by: str | None = None,
    ) -> JobFailure:
        """Recover a terminal failure.

        Raises:
            NotFoundError: If the failure does not exist here.
            ConflictError: If it is not terminal, or has already been recovered.
        """
        failure = await self._failures.require_in_org(organization_id, failure_id)
        if not failure.is_terminal:
            raise ConflictError(
                f"Failure {failure_id} is not terminal; it may still retry on its own."
            )
        if failure.recovered:
            raise ConflictError(f"Failure {failure_id} has already been recovered.")

        failure.recovered = True
        failure.recovered_at = datetime.now(UTC)
        failure.recovered_by = recovered_by
        failure.recovery_action = action
        updated = await self._failures.update(failure)

        job = await self._jobs.require_in_org(organization_id, failure.job_id)
        if action in _REDISPATCHING_ACTIONS:
            await self._executions.dispatch(organization_id, job.id, trigger_source="recovery")

        await self._publish_event(
            SchedulerRecoveredEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "job_id": str(job.id),
                    "failure_id": str(failure_id),
                    "recovery_action": str(action),
                },
            )
        )
        if job.owner_id:
            await self._notifications.send_recovery_completed(
                job.owner_id, job_name=job.name, action=str(action)
            )
        return updated

    async def list_unrecovered(self, organization_id: UUID) -> list[JobFailure]:
        """Every terminal failure nobody has recovered yet."""
        return await self._failures.list_unrecovered_terminal(organization_id)


__all__ = ["RecoveryService"]
