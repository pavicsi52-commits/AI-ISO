"""Automation execution engine: the run-level orchestrator.

Per docs/040 "EXECUTION ENGINE" "Support": Sequential Execution,
Parallel Execution, Conditional Execution (via per-target dispatch),
Checkpointing, Resume, Pause, Cancel, Timeout, Execution Priority.
:meth:`AutomationExecutionService.run_execution` is the one method
that actually dispatches a job's content -- everything else
(create/cancel/pause/resume) only ever mutates
:class:`~app.models.automation_execution.AutomationExecution`'s own
status; the queue worker that calls ``run_execution`` is
:mod:`app.workers.execution_worker`.

**Concurrency note**: dispatch calls (subprocess/SSH) for every target
in one batch run concurrently via ``asyncio.gather`` (bounded by
``max_parallel_targets``, "Parallel Execution"/"Fan-Out"), but every
database write happens afterward, one at a time -- a single
SQLAlchemy ``AsyncSession`` is not safe for concurrent use from
multiple coroutines, so persistence is deliberately kept sequential
while the genuinely slow part (the remote/local command itself) runs
in parallel.

**Checkpointing/Resume**: ``run_execution`` always re-derives which
targets already have a ``COMPLETED`` step before dispatching anything,
so calling it again after a pause only re-runs what's left ("Resume").
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.connectors.manager import ConnectorManager
from shared_core.events.base import DomainEvent
from shared_core.exceptions.dependency import DependencyError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.queue.retry import RetryPolicy

from app.dispatchers.execution_dispatcher import dispatch_execution
from app.events.automation_events import (
    AutomationCancelledEvent,
    AutomationCompletedEvent,
    AutomationFailedEvent,
    AutomationPausedEvent,
    AutomationResumedEvent,
    AutomationStartedEvent,
    ExecutionTimedOutEvent,
)
from app.models.automation_execution import AutomationExecution
from app.models.automation_execution_log import AutomationExecutionLog
from app.models.automation_execution_step import AutomationExecutionStep
from app.models.automation_output import AutomationOutput
from app.models.automation_result import AutomationResult
from app.models.automation_retry_history import AutomationRetryHistory
from app.models.automation_target import AutomationTarget
from app.models.enums import (
    ExecutionMode,
    ExecutionStatus,
    ExecutionStepStatus,
    FailureClassification,
    LogLevel,
    RetryStrategy,
)
from app.repositories.automation_execution import AutomationExecutionRepository
from app.repositories.automation_execution_log import AutomationExecutionLogRepository
from app.repositories.automation_execution_step import AutomationExecutionStepRepository
from app.repositories.automation_job import AutomationJobRepository
from app.repositories.automation_output import AutomationOutputRepository
from app.repositories.automation_result import AutomationResultRepository
from app.repositories.automation_retry_history import AutomationRetryHistoryRepository
from app.repositories.automation_target import AutomationTargetRepository
from app.runners.base import RunnerResult
from app.runners.exceptions import RunnerError
from app.secrets.credential_resolver import SecretCredentialResolver

EventPublisher = Callable[[DomainEvent], Awaitable[None]]

_ACTIVE_STATUSES = (ExecutionStatus.PENDING, ExecutionStatus.RUNNING, ExecutionStatus.PAUSED)
_STDOUT_LOG_LIMIT = 8192
_MAX_RETRY_ATTEMPTS = 3


def _classify_failure(exc: Exception) -> FailureClassification:
    if isinstance(exc, DependencyError):
        return FailureClassification.TRANSIENT
    if isinstance(exc, TimeoutError):
        return FailureClassification.TIMEOUT
    if isinstance(exc, RunnerError) and "timed out" in str(exc).lower():
        return FailureClassification.TIMEOUT
    return FailureClassification.PERMANENT


class AutomationExecutionService:
    """Creates, runs, and manages the lifecycle of automation executions."""

    def __init__(
        self,
        executions: AutomationExecutionRepository,
        steps: AutomationExecutionStepRepository,
        logs: AutomationExecutionLogRepository,
        outputs: AutomationOutputRepository,
        results: AutomationResultRepository,
        retry_history: AutomationRetryHistoryRepository,
        jobs: AutomationJobRepository,
        targets: AutomationTargetRepository,
        connector_manager: ConnectorManager,
        credentials: SecretCredentialResolver,
        *,
        max_parallel_targets: int = 20,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._executions = executions
        self._steps = steps
        self._logs = logs
        self._outputs = outputs
        self._results = results
        self._retry_history = retry_history
        self._jobs = jobs
        self._targets = targets
        self._connector_manager = connector_manager
        self._credentials = credentials
        self._max_parallel_targets = max_parallel_targets
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, execution_id: UUID) -> AutomationExecution:
        """Return the execution identified by *execution_id*.

        Raises:
            NotFoundError: If no such execution exists.
        """
        return await self._executions.require_by_id(execution_id)

    async def list_for_job(self, job_id: UUID) -> list[AutomationExecution]:
        """Every execution recorded for *job_id*, newest first."""
        return await self._executions.list_for_job(job_id)

    async def list_for_org(
        self, organization_id: UUID, *, status: ExecutionStatus | None = None
    ) -> list[AutomationExecution]:
        """Every execution for *organization_id*, newest first."""
        return await self._executions.list_for_org(organization_id, status=status)

    async def create_execution(
        self,
        job_id: UUID,
        *,
        target_ids: list[UUID],
        variables: dict[str, Any],
        execution_mode: ExecutionMode,
        timeout_seconds: int | None,
        triggered_by: UUID | None,
    ) -> AutomationExecution:
        """Record a new, not-yet-started execution ("Create"). The actual
        dispatch happens in :meth:`run_execution`, called by
        :mod:`app.workers.execution_worker` after this execution is
        enqueued.
        """
        job = await self._jobs.require_by_id(job_id)
        merged_variables = {**job.variables, **variables}
        execution = await self._executions.create(
            AutomationExecution(
                organization_id=job.organization_id,
                job_id=job_id,
                status=ExecutionStatus.PENDING,
                execution_mode=execution_mode,
                triggered_by=triggered_by,
                variables=merged_variables,
                timeout_seconds=timeout_seconds or job.timeout_seconds,
            )
        )
        if target_ids:
            execution.variables = {
                **execution.variables,
                "_target_ids": [str(t) for t in target_ids],
            }
            execution = await self._executions.update(execution)
        return execution

    async def run_execution(self, execution_id: UUID, *, caller_token: str) -> AutomationExecution:
        """Dispatch every not-yet-completed target for *execution_id* and
        finalize its outcome ("Execution").

        Raises:
            NotFoundError: If no such execution exists.
        """
        execution = await self._executions.require_by_id(execution_id)
        job = await self._jobs.require_by_id(execution.job_id)

        if execution.status == ExecutionStatus.PENDING:
            execution.status = ExecutionStatus.RUNNING
            execution.started_at = datetime.now(UTC)
            execution = await self._executions.update(execution)
            await self._publish(
                AutomationStartedEvent(
                    source_service="automation-service",
                    payload={"execution_id": str(execution.id), "job_id": str(job.id)},
                )
            )
        elif execution.status == ExecutionStatus.PAUSED:
            execution.status = ExecutionStatus.RUNNING
            execution = await self._executions.update(execution)

        target_id_strings = execution.variables.get("_target_ids", [])
        target_ids = [UUID(str(t)) for t in target_id_strings]
        resolved_targets = await self._targets.list_by_ids(target_ids) if target_ids else []

        existing_steps = await self._steps.list_for_execution(execution_id)
        completed_target_ids = {
            step.target_id
            for step in existing_steps
            if step.status == ExecutionStepStatus.COMPLETED
        }
        overall_success = all(
            step.status == ExecutionStepStatus.COMPLETED for step in existing_steps
        )

        pending_targets: list[AutomationTarget | None]
        if resolved_targets:
            pending_targets = [t for t in resolved_targets if t.id not in completed_target_ids]
        else:
            pending_targets = [] if existing_steps else [None]

        timeout = float(execution.timeout_seconds) if execution.timeout_seconds else None
        next_index = len(existing_steps)

        for batch_start in range(0, len(pending_targets), self._max_parallel_targets):
            execution = await self._executions.require_by_id(execution_id)
            if execution.status == ExecutionStatus.CANCELLED:
                break
            if execution.status == ExecutionStatus.PAUSED:
                return execution

            batch = pending_targets[batch_start : batch_start + self._max_parallel_targets]
            dispatch_outcomes = await asyncio.gather(
                *(
                    self._dispatch_with_retry(execution.id, job, target, timeout, caller_token)
                    for target in batch
                )
            )
            for target, (result, error) in zip(batch, dispatch_outcomes, strict=True):
                await self._record_step(execution, job, target, next_index, result, error)
                next_index += 1
                if error is not None or (result is not None and not result.succeeded):
                    overall_success = False

        return await self._finalize_execution(execution, job, overall_success)

    async def _dispatch_with_retry(
        self,
        execution_id: UUID,
        job: Any,
        target: AutomationTarget | None,
        timeout_seconds: float | None,
        caller_token: str,
    ) -> tuple[RunnerResult | None, Exception | None]:
        policy = RetryPolicy(max_attempts=_MAX_RETRY_ATTEMPTS)
        attempt = 1
        last_error: Exception | None = None
        while attempt <= policy.max_attempts:
            try:
                result = await dispatch_execution(
                    playbook_type=job.playbook_type,
                    content=job.content,
                    target=target,
                    timeout_seconds=timeout_seconds,
                    connector_manager=self._connector_manager,
                    credentials=self._credentials,
                    caller_token=caller_token,
                )
            except Exception as exc:
                last_error = exc
                classification = _classify_failure(exc)
                await self._retry_history.create(
                    AutomationRetryHistory(
                        organization_id=job.organization_id,
                        execution_id=execution_id,
                        attempt_number=attempt,
                        strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
                        classification=classification,
                        succeeded=False,
                        attempted_at=datetime.now(UTC),
                    )
                )
                is_final_attempt = attempt == policy.max_attempts
                if classification is not FailureClassification.TRANSIENT or is_final_attempt:
                    return None, exc
                await asyncio.sleep(policy.delay_for(attempt))
                attempt += 1
                continue
            return result, None
        return None, last_error

    async def _record_step(
        self,
        execution: AutomationExecution,
        job: Any,
        target: AutomationTarget | None,
        step_index: int,
        result: RunnerResult | None,
        error: Exception | None,
    ) -> AutomationExecutionStep:
        now = datetime.now(UTC)
        step = await self._steps.create(
            AutomationExecutionStep(
                organization_id=job.organization_id,
                execution_id=execution.id,
                step_index=step_index,
                name=target.name if target is not None else "local",
                status=ExecutionStepStatus.RUNNING,
                target_id=target.id if target is not None else None,
                started_at=now,
            )
        )
        if error is not None:
            step.status = ExecutionStepStatus.FAILED
            step.completed_at = datetime.now(UTC)
            step.error_message = str(error)[:2048]
            await self._steps.update(step)
            await self._logs.create(
                AutomationExecutionLog(
                    organization_id=job.organization_id,
                    execution_id=execution.id,
                    step_id=step.id,
                    level=LogLevel.ERROR,
                    message=str(error),
                    logged_at=datetime.now(UTC),
                )
            )
            return step

        if result is None:
            raise RuntimeError("_record_step called with neither a result nor an error.")
        step.status = (
            ExecutionStepStatus.COMPLETED if result.succeeded else ExecutionStepStatus.FAILED
        )
        step.completed_at = datetime.now(UTC)
        step.output = {
            "exit_code": result.exit_code,
            "duration_seconds": result.duration_seconds,
        }
        await self._steps.update(step)

        await self._logs.create(
            AutomationExecutionLog(
                organization_id=job.organization_id,
                execution_id=execution.id,
                step_id=step.id,
                level=LogLevel.INFO if result.succeeded else LogLevel.ERROR,
                message=(result.stdout or result.stderr or "(no output)")[:_STDOUT_LOG_LIMIT],
                logged_at=datetime.now(UTC),
            )
        )
        await self._outputs.create(
            AutomationOutput(
                organization_id=job.organization_id,
                execution_id=execution.id,
                step_id=step.id,
                key="exit_code",
                value=result.exit_code,
            )
        )
        return step

    async def _finalize_execution(
        self, execution: AutomationExecution, job: Any, overall_success: bool
    ) -> AutomationExecution:
        execution = await self._executions.require_by_id(execution.id)
        if execution.status == ExecutionStatus.CANCELLED:
            await self._publish(
                AutomationCancelledEvent(
                    source_service="automation-service",
                    payload={"execution_id": str(execution.id), "job_id": str(job.id)},
                )
            )
            return execution

        execution.status = ExecutionStatus.COMPLETED if overall_success else ExecutionStatus.FAILED
        execution.completed_at = datetime.now(UTC)
        if not overall_success:
            execution.error_message = "One or more targets failed."
        execution = await self._executions.update(execution)

        await self._results.create(
            AutomationResult(
                organization_id=job.organization_id,
                execution_id=execution.id,
                success=overall_success,
                summary=(
                    "All targets succeeded." if overall_success else "One or more targets failed."
                ),
                metrics={},
                completed_at=datetime.now(UTC),
            )
        )

        if overall_success:
            await self._publish(
                AutomationCompletedEvent(
                    source_service="automation-service",
                    payload={"execution_id": str(execution.id), "job_id": str(job.id)},
                )
            )
        else:
            await self._publish(
                AutomationFailedEvent(
                    source_service="automation-service",
                    payload={"execution_id": str(execution.id), "job_id": str(job.id)},
                )
            )
        return execution

    async def cancel_job_execution(self, job_id: UUID) -> AutomationExecution:
        """Cancel *job_id*'s currently active execution ("Cancel").

        Raises:
            NotFoundError: If *job_id* has no active execution.
        """
        execution = await self._get_active_execution_for_job(job_id)
        execution.status = ExecutionStatus.CANCELLED
        execution.completed_at = datetime.now(UTC)
        execution = await self._executions.update(execution)
        await self._publish(
            AutomationCancelledEvent(
                source_service="automation-service",
                payload={"execution_id": str(execution.id), "job_id": str(job_id)},
            )
        )
        return execution

    async def pause_job_execution(self, job_id: UUID) -> AutomationExecution:
        """Pause *job_id*'s currently running execution ("Pause").

        Raises:
            NotFoundError: If *job_id* has no running execution.
        """
        execution = await self._get_active_execution_for_job(
            job_id, statuses={ExecutionStatus.RUNNING}
        )
        execution.status = ExecutionStatus.PAUSED
        execution = await self._executions.update(execution)
        await self._publish(
            AutomationPausedEvent(
                source_service="automation-service",
                payload={"execution_id": str(execution.id), "job_id": str(job_id)},
            )
        )
        return execution

    async def resume_job_execution(self, job_id: UUID) -> AutomationExecution:
        """Mark *job_id*'s paused execution as ready to resume ("Resume").

        Raises:
            NotFoundError: If *job_id* has no paused execution.
        """
        execution = await self._get_active_execution_for_job(
            job_id, statuses={ExecutionStatus.PAUSED}
        )
        await self._publish(
            AutomationResumedEvent(
                source_service="automation-service",
                payload={"execution_id": str(execution.id), "job_id": str(job_id)},
            )
        )
        return execution

    async def mark_timed_out(self, execution_id: UUID) -> AutomationExecution:
        """Mark an execution as having exceeded its own timeout ("Timeout")."""
        execution = await self._executions.require_by_id(execution_id)
        execution.status = ExecutionStatus.TIMED_OUT
        execution.completed_at = datetime.now(UTC)
        execution.error_message = "Execution exceeded its own timeout."
        execution = await self._executions.update(execution)
        await self._publish(
            ExecutionTimedOutEvent(
                source_service="automation-service",
                payload={"execution_id": str(execution.id), "job_id": str(execution.job_id)},
            )
        )
        return execution

    async def _get_active_execution_for_job(
        self, job_id: UUID, *, statuses: set[ExecutionStatus] | None = None
    ) -> AutomationExecution:
        allowed = statuses or set(_ACTIVE_STATUSES)
        executions = await self._executions.list_for_job(job_id)
        for execution in executions:
            if execution.status in allowed:
                return execution
        raise NotFoundError(f"Job '{job_id}' has no active execution in status {allowed}.")


__all__ = ["AutomationExecutionService"]
