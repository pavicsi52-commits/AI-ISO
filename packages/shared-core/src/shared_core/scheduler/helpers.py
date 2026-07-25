"""Small, dependency-free utility functions shared across the framework."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from shared_core.enums.job_status import JobStatus
from shared_core.scheduler.job import Job

_DUE_STATUSES = frozenset({JobStatus.SCHEDULED, JobStatus.RETRYING})
_SECONDS_PER_MINUTE = 60
_MINUTES_PER_HOUR = 60


def format_duration(seconds: float) -> str:
    """Format a duration in seconds as a compact human-readable string (e.g. ``"2m 30s"``)."""
    total_seconds = round(seconds)
    if total_seconds < _SECONDS_PER_MINUTE:
        return f"{total_seconds}s"
    minutes, secs = divmod(total_seconds, _SECONDS_PER_MINUTE)
    if minutes < _MINUTES_PER_HOUR:
        return f"{minutes}m {secs}s" if secs else f"{minutes}m"
    hours, mins = divmod(minutes, _MINUTES_PER_HOUR)
    return f"{hours}h {mins}m" if mins else f"{hours}h"


def is_due(job: Job, *, now: datetime | None = None) -> bool:
    """Whether *job* is currently due, evaluated in isolation (no registry/dependency check).

    A lightweight check for a single :class:`~shared_core.scheduler.job.Job`
    object -- for deciding which *registered* jobs are due across a whole
    fleet (including dependency satisfaction), use
    :meth:`shared_core.scheduler.engine.SchedulerEngine.due_jobs` instead.
    """
    moment = now or datetime.now(UTC)
    return job.status in _DUE_STATUSES and job.next_run is not None and job.next_run <= moment


def job_summary(job: Job) -> dict[str, Any]:
    """A JSON-serializable summary of *job*, omitting the non-serializable ``fn``."""
    return {
        "job_id": job.job_id,
        "job_name": job.job_name,
        "job_type": job.job_type.value,
        "status": job.status.value,
        "priority": job.priority.value,
        "next_run": job.next_run.isoformat() if job.next_run else None,
        "last_run": job.last_run.isoformat() if job.last_run else None,
    }


__all__ = ["format_duration", "is_due", "job_summary"]
