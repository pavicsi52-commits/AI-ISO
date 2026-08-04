"""Dispatching a job's execution, and handling what happens when it fails.

**This service dispatches; it does not perform a job's own work.** The
"unit of work" for every job type this platform defines is publishing
``JobStarted`` with the job's payload -- whichever platform service owns
that job type (docs/054's own "PLATFORM INTEGRATIONS") is the one that
actually acts on it, per this prompt's own "DO NOT IMPLEMENT ...
Business-specific Scheduling Logic." A dispatch that successfully
publishes is recorded ``COMPLETED``; one that fails to publish (or is
refused before it gets that far -- an unsatisfied dependency, a deleted
job) is recorded ``FAILED`` and handed to the same retry/dead-letter
decision every other failure goes through.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.logging.logger import get_logger

from app.events.scheduler_events import (
    SOURCE_SERVICE,
    JobCancelledEvent,
    JobCompletedEvent,
    JobFailedEvent,
    JobRetriedEvent,
    JobStartedEvent,
)
from app.models.enums import (
    OPEN_EXECUTION_STATUSES,
    ExecutionStatus,
    RetryType,
    ScheduledJobStatus,
    execution_status_of,
    retry_type_of,
    scheduled_job_status_of,
)
from app.models.execution import JobExecution, JobExecutionLog
from app.models.history import JobFailure
from app.models.job import ScheduledJob
from app.notifications.scheduler_notifications import SchedulerNotificationService
from app.repositories.execution import JobExecutionLogRepository, JobExecutionRepository
from app.repositories.history import JobFailureRepository
from app.repositories.job import ScheduledJobRepository
from app.repositories.retry import JobRetryPolicyRepository
from app.retries.engine import compute_delay_seconds, should_retry
from app.scheduling.engine import validate_execution_transition
from app.services.job import JobService
from app.types import EventPublisher

logger = get_logger("app.services.execution")


class ExecutionService:
    """Dispatches job executions and drives their status through to a terminal outcome."""

    def __init__(
        self,
        executions: JobExecutionRepository,
        logs: JobExecutionLogRepository,
        failures: JobFailureRepository,
        jobs: ScheduledJobRepository,
        retry_policies: JobRetryPolicyRepository,
        job_service: JobService,
        notifications: SchedulerNotificationService,
        *,
        publish_event: EventPublisher | None = None,
        default_max_attempts: int = 3,
        default_base_delay_seconds: float = 5.0,
        default_max_delay_seconds: float = 300.0,
    ) -> None:
        self._executions = executions
        self._logs = logs
        self._failures = failures
        self._jobs = jobs
        self._retry_policies = retry_policies
        self._job_service = job_service
        self._notifications = notifications
        self._publish = publish_event
        self._default_max_attempts = default_max_attempts
        self._default_base_delay_seconds = default_base_delay_seconds
        self._default_max_delay_seconds = default_max_delay_seconds

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def dispatch(
        self,
        organization_id: UUID,
        job_id: UUID,
        *,
        trigger_source: str,
        attempt_number: int = 1,
    ) -> JobExecution:
        """Dispatch one execution of a job.

        Raises:
            NotFoundError: If the job does not exist here.
            ConflictError: If the job has been deleted.
        """
        moment = datetime.now(UTC)
        job = await self._jobs.require_in_org(organization_id, job_id)
        if scheduled_job_status_of(job.status) is ScheduledJobStatus.DELETED:
            raise ConflictError(f"{job.name} has been deleted; it cannot be dispatched.")

        execution = await self._executions.create(
            JobExecution(
                organization_id=organization_id,
                job_id=job_id,
                status=ExecutionStatus.QUEUED,
                trigger_source=trigger_source,
                priority_snapshot=job.priority,
                payload_snapshot=dict(job.payload),
                queued_at=moment,
                attempt_number=attempt_number,
            )
        )
        validate_execution_transition(ExecutionStatus.QUEUED, ExecutionStatus.RUNNING)
        execution.status = ExecutionStatus.RUNNING
        execution.started_at = moment
        await self._executions.update(execution)

        await self._publish_event(
            JobStartedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "job_id": str(job_id),
                    "execution_id": str(execution.id),
                    "job_type": str(job.job_type),
                    "payload": execution.payload_snapshot,
                    "attempt_number": attempt_number,
                },
            )
        )

        try:
            finished = datetime.now(UTC)
            validate_execution_transition(ExecutionStatus.RUNNING, ExecutionStatus.COMPLETED)
            execution.status = ExecutionStatus.COMPLETED
            execution.completed_at = finished
            execution.duration_ms = (finished - moment).total_seconds() * 1_000
            await self._executions.update(execution)

            await self._job_service.record_run(organization_id, job_id, ran_at=finished)
            await self._publish_event(
                JobCompletedEvent(
                    source_service=SOURCE_SERVICE,
                    payload={
                        "organization_id": str(organization_id),
                        "job_id": str(job_id),
                        "execution_id": str(execution.id),
                    },
                )
            )
            if job.owner_id:
                await self._notifications.send_job_completed(job.owner_id, job_name=job.name)
            return execution
        except Exception as exc:
            await self._handle_failure(organization_id, job, execution, error=str(exc))
            return execution

    async def _handle_failure(
        self, organization_id: UUID, job: ScheduledJob, execution: JobExecution, *, error: str
    ) -> None:
        finished = datetime.now(UTC)
        validate_execution_transition(ExecutionStatus.RUNNING, ExecutionStatus.FAILED)
        execution.status = ExecutionStatus.FAILED
        execution.completed_at = finished
        execution.error = error
        await self._executions.update(execution)
        await self._job_service.record_failure(organization_id, job.id)

        policy = await self._retry_policies.get_for_job(organization_id, job.id)
        max_attempts = policy.max_attempts if policy else self._default_max_attempts
        base_delay = policy.base_delay_seconds if policy else self._default_base_delay_seconds
        max_delay = policy.max_delay_seconds if policy else self._default_max_delay_seconds
        retry_type = retry_type_of(policy.retry_type) if policy else RetryType.EXPONENTIAL_BACKOFF
        retry_conditions = policy.retry_conditions if policy else {}
        dead_letter_enabled = policy.dead_letter_enabled if policy else True

        will_retry = dead_letter_enabled and should_retry(
            attempt_number=execution.attempt_number,
            max_attempts=max_attempts,
            exit_code=execution.exit_code,
            error_message=error,
            retry_conditions=retry_conditions,
        )
        retry_at = None
        if will_retry:
            delay = compute_delay_seconds(
                retry_type, execution.attempt_number, base_seconds=base_delay, max_seconds=max_delay
            )
            retry_at = finished + timedelta(seconds=delay)

        await self._failures.create(
            JobFailure(
                organization_id=organization_id,
                job_id=job.id,
                execution_id=execution.id,
                occurred_at=finished,
                failure_reason=error[:512],
                error_detail=error,
                is_terminal=not will_retry,
                retry_at=retry_at,
            )
        )

        if will_retry:
            await self._publish_event(
                JobRetriedEvent(
                    source_service=SOURCE_SERVICE,
                    payload={
                        "organization_id": str(organization_id),
                        "job_id": str(job.id),
                        "execution_id": str(execution.id),
                        "next_attempt": execution.attempt_number + 1,
                        "retry_at": retry_at.isoformat() if retry_at else None,
                    },
                )
            )
            if job.owner_id:
                await self._notifications.send_retry_started(
                    job.owner_id,
                    job_name=job.name,
                    attempt_number=execution.attempt_number + 1,
                    max_attempts=max_attempts,
                )
        else:
            await self._publish_event(
                JobFailedEvent(
                    source_service=SOURCE_SERVICE,
                    payload={
                        "organization_id": str(organization_id),
                        "job_id": str(job.id),
                        "execution_id": str(execution.id),
                        "error": error,
                    },
                )
            )
            if job.owner_id:
                await self._notifications.send_job_failed(
                    job.owner_id, job_name=job.name, error=error
                )

    async def retry_failure(self, organization_id: UUID, failure_id: UUID) -> JobExecution:
        """Dispatch the next attempt for a failure whose retry delay has elapsed.

        Raises:
            NotFoundError: If the failure does not exist here.
            ConflictError: If it has already been retried, or is terminal.
        """
        failure = await self._failures.require_in_org(organization_id, failure_id)
        if failure.retried:
            raise ConflictError(f"Failure {failure_id} has already been retried.")
        if failure.is_terminal:
            raise ConflictError(f"Failure {failure_id} is terminal; it needs manual recovery.")

        prior = await self._executions.require_in_org(organization_id, failure.execution_id)
        failure.retried = True
        await self._failures.update(failure)
        return await self.dispatch(
            organization_id,
            failure.job_id,
            trigger_source=prior.trigger_source,
            attempt_number=prior.attempt_number + 1,
        )

    async def cancel_open_for_job(self, organization_id: UUID, job_id: UUID) -> int:
        """Cancel every execution of one job still in flight. Returns how many."""
        open_executions = await self._executions.list_for_job(organization_id, job_id, limit=1_000)
        cancelled = 0
        for execution in open_executions:
            status = execution_status_of(execution.status)
            if status not in OPEN_EXECUTION_STATUSES:
                continue
            validate_execution_transition(status, ExecutionStatus.CANCELLED)
            execution.status = ExecutionStatus.CANCELLED
            execution.completed_at = datetime.now(UTC)
            await self._executions.update(execution)
            await self._publish_event(
                JobCancelledEvent(
                    source_service=SOURCE_SERVICE,
                    payload={
                        "organization_id": str(organization_id),
                        "job_id": str(job_id),
                        "execution_id": str(execution.id),
                    },
                )
            )
            cancelled += 1
        return cancelled

    async def get(self, organization_id: UUID, execution_id: UUID) -> JobExecution:
        """One execution.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._executions.require_in_org(organization_id, execution_id)

    async def list_for_job(
        self, organization_id: UUID, job_id: UUID, *, limit: int = 200, offset: int = 0
    ) -> list[JobExecution]:
        """Every execution of one job, newest first."""
        return await self._executions.list_for_job(
            organization_id, job_id, limit=limit, offset=offset
        )

    async def list_filtered(
        self,
        organization_id: UUID,
        *,
        status: ExecutionStatus | None = None,
        job_id: UUID | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[JobExecution]:
        """Executions matching a caller's filters."""
        return await self._executions.list_filtered(
            organization_id, status=status, job_id=job_id, limit=limit, offset=offset
        )

    async def list_logs(self, organization_id: UUID, execution_id: UUID) -> list[JobExecutionLog]:
        """Every log line for one execution."""
        return await self._logs.list_for_execution(organization_id, execution_id)

    async def add_log(
        self, organization_id: UUID, execution_id: UUID, *, level: str = "info", message: str
    ) -> JobExecutionLog:
        """Append one log line to an execution."""
        return await self._logs.create(
            JobExecutionLog(
                organization_id=organization_id,
                execution_id=execution_id,
                occurred_at=datetime.now(UTC),
                level=level,
                message=message,
            )
        )


__all__ = ["ExecutionService"]
