"""Job registry.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "ACCEPTANCE
CRITERIA": Job Registry. The in-process, authoritative store of every
job known to this scheduler node: register/unregister, lookup, listing,
and the status transitions that make up a job's "JOB LIFECYCLE".
Persistence across restarts is a concern for whatever repository layer
wraps this registry in a running service -- the same "purely
in-process" pattern already used by
:class:`shared_core.telemetry.analytics.TraceRecorder` and
:class:`shared_core.notifications.history.HistoryStore`.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from shared_core.enums.job_status import JobStatus
from shared_core.scheduler.exceptions import JobNotFoundError
from shared_core.scheduler.job import Job

_TERMINAL_STATUSES = frozenset({JobStatus.CANCELLED, JobStatus.EXPIRED, JobStatus.ARCHIVED})


class JobRegistry:
    """The authoritative in-process store of registered jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def register(self, job: Job) -> None:
        """Add or replace *job* ("Job Registration")."""
        self._jobs[job.job_id] = job

    def unregister(self, job_id: str) -> None:
        """Remove a job entirely. A no-op if it isn't registered."""
        self._jobs.pop(job_id, None)

    def get(self, job_id: str) -> Job:
        """Look up a job by id.

        Raises:
            JobNotFoundError: If no job with *job_id* is registered.
        """
        try:
            return self._jobs[job_id]
        except KeyError as exc:
            raise JobNotFoundError(f"Job '{job_id}' is not registered.") from exc

    def status_of(self, job_id: str) -> JobStatus | None:
        """The job's current status, or ``None`` if unregistered.

        Matches :data:`shared_core.scheduler.dependency.JobStatusLookup`'s
        shape, so a registry can be passed directly to
        :meth:`~shared_core.scheduler.dependency.DependencyGraph.is_satisfied`.
        """
        job = self._jobs.get(job_id)
        return job.status if job is not None else None

    def list_jobs(self) -> list[Job]:
        """Every currently registered job."""
        return list(self._jobs.values())

    def list_by_status(self, status: JobStatus) -> list[Job]:
        """Every registered job currently in *status*."""
        return [job for job in self._jobs.values() if job.status == status]

    def transition(self, job_id: str, status: JobStatus, **updates: Any) -> Job:
        """Move a job to *status*, applying any other field *updates* at once.

        Raises:
            JobNotFoundError: If no job with *job_id* is registered.
        """
        current = self.get(job_id)
        updated = replace(current, status=status, updated_at=datetime.now(UTC), **updates)
        self._jobs[job_id] = updated
        return updated

    def pause(self, job_id: str) -> Job:
        """Suspend a job ("Pause")."""
        return self.transition(job_id, JobStatus.PAUSED)

    def resume(self, job_id: str) -> Job:
        """Resume a paused job ("Resume")."""
        return self.transition(job_id, JobStatus.SCHEDULED)

    def cancel(self, job_id: str) -> Job:
        """Cancel a job ("Cancellation")."""
        return self.transition(job_id, JobStatus.CANCELLED)

    def is_terminal(self, job_id: str) -> bool:
        """Whether the job has reached a state it will never leave on its own."""
        return self.get(job_id).status in _TERMINAL_STATUSES


__all__ = ["JobRegistry"]
