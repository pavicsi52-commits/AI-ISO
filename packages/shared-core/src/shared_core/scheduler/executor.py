"""Job executor.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "JOB EXECUTION":
Async Execution, Exclusive Execution, Timeout, Cancellation; "RETRY
POLICY": Immediate Retry, Fixed Delay, Exponential Backoff, Maximum
Attempts. Runs a single job's ``fn``, applying its ``timeout_seconds``
and ``retry_policy``, and (when a Redis client is supplied) its
"Exclusive Execution" lock -- reusing
:mod:`shared_core.scheduler.locking` directly rather than duplicating
locking here.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from redis.asyncio import Redis

from shared_core.scheduler.constants import DEFAULT_JOB_LOCK_TTL_SECONDS
from shared_core.scheduler.exceptions import JobExecutionError, JobTimeoutError
from shared_core.scheduler.job import Job
from shared_core.scheduler.locking import exclusive_job_execution


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """The outcome of one call to :meth:`JobExecutor.execute`."""

    job_id: str
    succeeded: bool
    attempts: int
    started_at: datetime
    finished_at: datetime
    error: str | None = None

    @property
    def duration_seconds(self) -> float:
        """Wall-clock time the execution (across every retry attempt) took."""
        return (self.finished_at - self.started_at).total_seconds()


class JobExecutor:
    """Runs a job's ``fn`` with timeout and retry, optionally under an exclusive lock."""

    def __init__(self, *, lock_client: Redis | None = None) -> None:
        self._lock_client = lock_client

    async def execute(self, job: Job) -> ExecutionResult:
        """Run *job*, retrying per its ``retry_policy`` on a retryable failure.

        A skipped run (another node already holds the job's exclusive
        lock) is reported as a failed, zero-attempt result rather than
        raising, so a caller can distinguish "someone else is running
        this" from a genuine execution error -- "Prevent Duplicate
        Execution".
        """
        if self._lock_client is None:
            return await self._run_with_retry(job)
        async with exclusive_job_execution(
            self._lock_client, job.job_id, ttl_seconds=self._lock_ttl(job)
        ) as acquired:
            if not acquired:
                now = datetime.now(UTC)
                return ExecutionResult(
                    job_id=job.job_id,
                    succeeded=False,
                    attempts=0,
                    started_at=now,
                    finished_at=now,
                    error="Exclusive lock held by another worker.",
                )
            return await self._run_with_retry(job)

    def _lock_ttl(self, job: Job) -> int:
        if job.timeout_seconds is not None:
            return max(int(job.timeout_seconds), 1)
        return DEFAULT_JOB_LOCK_TTL_SECONDS

    async def _run_with_retry(self, job: Job) -> ExecutionResult:
        started_at = datetime.now(UTC)
        policy = job.retry_policy
        last_error: Exception | None = None
        attempts = 0
        for attempt in range(1, policy.max_attempts + 1):
            attempts = attempt
            try:
                await self._run_once(job)
            except Exception as exc:
                last_error = exc
                is_final_attempt = attempt == policy.max_attempts
                if not policy.classify(exc) or is_final_attempt:
                    break
                await asyncio.sleep(policy.delay_for(attempt))
                continue
            return ExecutionResult(
                job_id=job.job_id,
                succeeded=True,
                attempts=attempts,
                started_at=started_at,
                finished_at=datetime.now(UTC),
            )
        return ExecutionResult(
            job_id=job.job_id,
            succeeded=False,
            attempts=attempts,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            error=str(last_error) if last_error is not None else None,
        )

    async def _run_once(self, job: Job) -> None:
        try:
            if job.timeout_seconds is not None:
                await asyncio.wait_for(job.fn(job), timeout=job.timeout_seconds)
            else:
                await job.fn(job)
        except TimeoutError as exc:
            raise JobTimeoutError(
                f"Job '{job.job_id}' exceeded its {job.timeout_seconds}s timeout."
            ) from exc
        except Exception as exc:
            raise JobExecutionError(f"Job '{job.job_id}' failed: {exc}") from exc


__all__ = ["ExecutionResult", "JobExecutor"]
