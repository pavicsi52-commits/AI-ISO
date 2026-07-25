"""Scheduler audit trail.

Per docs/026_Enterprise_Scheduler_Framework.md.txt "AUDIT": Job
Registration, Modification, Deletion, Execution, Retry, Pause, Resume,
Cancellation. Emitted as structured log events via
:meth:`shared_core.logging.logger.AIIOSLogger.audit` (Prompt 014) rather
than persisted to a database table -- same reasoning as
:mod:`shared_core.events.audit`/:mod:`shared_core.database.audit`: this
framework must not create business tables (docs/026 "DO NOT
IMPLEMENT"), and an append-only audit trail is exactly what structured
logging already covers.
"""

from __future__ import annotations

from shared_core.logging.logger import get_logger

logger = get_logger("shared_core.scheduler.audit")


def audit_registration(job_id: str, job_name: str, *, actor_id: str | None = None) -> None:
    """Record that a job was registered ("Job Registration")."""
    logger.audit("scheduler.job.register", actor_id=actor_id, resource=job_id, job_name=job_name)


def audit_modification(job_id: str, *, actor_id: str | None = None, **changes: object) -> None:
    """Record that a job was modified ("Modification")."""
    logger.audit("scheduler.job.modify", actor_id=actor_id, resource=job_id, changes=dict(changes))


def audit_deletion(job_id: str, *, actor_id: str | None = None) -> None:
    """Record that a job was deleted ("Deletion")."""
    logger.audit("scheduler.job.delete", actor_id=actor_id, resource=job_id)


def audit_execution(
    job_id: str, *, worker_node_id: str, outcome: str, attempts: int, error: str | None = None
) -> None:
    """Record a job execution's outcome ("Execution")."""
    logger.audit(
        "scheduler.job.execute",
        actor_id=worker_node_id,
        resource=job_id,
        outcome=outcome,
        attempts=attempts,
        error=error,
    )


def audit_retry(job_id: str, *, attempt: int, actor_id: str | None = None) -> None:
    """Record that a job is being retried ("Retry")."""
    logger.audit("scheduler.job.retry", actor_id=actor_id, resource=job_id, attempt=attempt)


def audit_pause(job_id: str, *, actor_id: str | None = None) -> None:
    """Record that a job was paused ("Pause")."""
    logger.audit("scheduler.job.pause", actor_id=actor_id, resource=job_id)


def audit_resume(job_id: str, *, actor_id: str | None = None) -> None:
    """Record that a job was resumed ("Resume")."""
    logger.audit("scheduler.job.resume", actor_id=actor_id, resource=job_id)


def audit_cancellation(job_id: str, *, actor_id: str | None = None) -> None:
    """Record that a job was cancelled ("Cancellation")."""
    logger.audit("scheduler.job.cancel", actor_id=actor_id, resource=job_id)


__all__ = [
    "audit_cancellation",
    "audit_deletion",
    "audit_execution",
    "audit_modification",
    "audit_pause",
    "audit_registration",
    "audit_resume",
    "audit_retry",
]
