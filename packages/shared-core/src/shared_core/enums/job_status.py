"""Background job status enumeration."""

from enum import StrEnum


class JobStatus(StrEnum):
    """Lifecycle states for asynchronous jobs.

    The original seven values (docs/006_API_Design_Master.md.txt) cover
    a generic async job; docs/026_Enterprise_Scheduler_Framework.md.txt
    "JOB LIFECYCLE" needs five more scheduler-specific states
    (Registered/Scheduled -- distinct pre-queue stages a generic job
    response never needed -- plus Retrying/Paused/Expired/Archived).
    Additive, not a replacement: kept every original value (one existing
    call site, docs/012's `JobResponse`) rather than renaming any of
    them to match, the same judgment call as Prompt 021's `Priority` and
    Prompt 023's `HealthStatus` extensions.
    """

    REGISTERED = "registered"
    SCHEDULED = "scheduled"
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    EXPIRED = "expired"
    ARCHIVED = "archived"
