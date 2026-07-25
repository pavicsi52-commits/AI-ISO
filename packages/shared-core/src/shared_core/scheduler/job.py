"""Job model.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "JOB MODEL" and
"JOB TYPES".
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from shared_core.enums.job_status import JobStatus
from shared_core.enums.priority import Priority
from shared_core.queue.retry import RetryPolicy
from shared_core.scheduler.retry import job_retry_policy
from shared_core.scheduler.schedule import Schedule


class JobType(StrEnum):
    """Every job type docs/026 "JOB TYPES" names."""

    ONE_TIME = "one_time"
    RECURRING = "recurring"
    CRON = "cron"
    FIXED_INTERVAL = "fixed_interval"
    DELAYED = "delayed"
    WORKFLOW_TIMER = "workflow_timer"
    MAINTENANCE = "maintenance"
    BACKGROUND = "background"
    SYSTEM = "system"
    AUTOMATION = "automation"
    VALIDATION = "validation"
    MONITORING = "monitoring"
    AI = "ai"
    CLEANUP = "cleanup"
    BACKUP = "backup"
    IMPORT = "import"
    EXPORT = "export"
    REPORT = "report"


JobFn = Callable[["Job"], Awaitable[None]]


def new_job_id() -> str:
    """Generate a new, unique job ID."""
    return str(uuid.uuid4())


@dataclass(slots=True)
class Job:
    """Every field docs/026 "JOB MODEL" requires, plus the callable it actually runs.

    ``fn`` isn't part of the documented field list -- a job is nothing
    without something to execute, and this framework's job registry
    associates a name with a real, awaitable callable
    (:mod:`shared_core.scheduler.executor` calls it), not just data.
    """

    job_id: str
    job_name: str
    job_type: JobType
    fn: JobFn
    schedule: Schedule
    organization_id: str | None = None
    project_id: str | None = None
    owner: str | None = None
    priority: Priority = Priority.NORMAL
    status: JobStatus = JobStatus.REGISTERED
    timezone: str = "UTC"
    retry_policy: RetryPolicy = field(default_factory=job_retry_policy)
    timeout_seconds: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_run: datetime | None = None
    next_run: datetime | None = None


def build_job(
    *, job_name: str, job_type: JobType, fn: JobFn, schedule: Schedule, **fields: Any
) -> Job:
    """Build a :class:`Job` with a freshly generated ID."""
    return Job(
        job_id=new_job_id(),
        job_name=job_name,
        job_type=job_type,
        fn=fn,
        schedule=schedule,
        **fields,
    )


__all__ = ["Job", "JobFn", "JobType", "build_job", "new_job_id"]
