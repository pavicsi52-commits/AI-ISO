"""``job_history`` and ``job_failures``.

``job_history`` is the structured status-transition ledger for a job
*definition* (registered, activated, paused, resumed, disabled,
deleted) -- distinct from ``scheduler_audit``, which is the broader
free-text audit trail across every entity type in this service, and
distinct from ``job_executions``, which is one row per actual *run*, not
per definition-level status change.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RecoveryAction


class JobHistory(BaseModel):
    """``job_history`` -- one status transition a job definition went through."""

    __tablename__ = "job_history"
    __table_args__ = (Index("ix_job_history_job", "organization_id", "job_id"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scheduled_jobs.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[str | None] = mapped_column(String(32), default=None)
    to_status: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[str | None] = mapped_column(String(255), default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)


class JobFailure(BaseModel):
    """``job_failures`` -- one execution's failure, and how it was (or wasn't) recovered."""

    __tablename__ = "job_failures"
    __table_args__ = (
        Index("ix_job_failure_job", "organization_id", "job_id"),
        Index("ix_job_failure_execution", "organization_id", "execution_id"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scheduled_jobs.id", ondelete="CASCADE"), index=True
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_executions.id", ondelete="CASCADE"), index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    failure_reason: Mapped[str] = mapped_column(String(512))
    error_detail: Mapped[str | None] = mapped_column(Text, default=None)

    is_terminal: Mapped[bool] = mapped_column(Boolean, default=False)
    """Set once retries are exhausted -- this failure is not going to
    self-heal on its own; someone or something has to act on it."""

    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    """When the retry sweep should attempt this job again -- ``None``
    once ``is_terminal`` is set. Computed at failure time from the
    job's retry policy, not re-derived at sweep time, so a policy an
    operator edits mid-backoff does not retroactively rewrite a delay
    already committed to."""

    retried: Mapped[bool] = mapped_column(Boolean, default=False)
    """Whether the retry sweep has already dispatched the next attempt
    for this failure -- guards against dispatching it twice if a sweep
    tick overlaps its own previous one."""

    recovery_action: Mapped[RecoveryAction | None] = mapped_column(String(32), default=None)
    recovered: Mapped[bool] = mapped_column(Boolean, default=False)
    recovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    recovered_by: Mapped[str | None] = mapped_column(String(255), default=None)


__all__ = ["JobFailure", "JobHistory"]
