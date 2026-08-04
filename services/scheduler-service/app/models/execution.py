"""``job_executions`` and ``job_execution_logs`` -- one run's own record.

Every field docs/054 "EXECUTION HISTORY" asks tracked: execution time,
duration, trigger source, worker, node, status, retries, logs,
artifacts, exit code, metadata.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ExecutionStatus, JobPriority


class JobExecution(BaseModel):
    """``job_executions`` -- one dispatch of one job."""

    __tablename__ = "job_executions"
    __table_args__ = (
        Index("ix_job_execution_job", "organization_id", "job_id"),
        Index("ix_job_execution_org_status", "organization_id", "status"),
        Index("ix_job_execution_queued", "organization_id", "queued_at"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scheduled_jobs.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        String(32), default=ExecutionStatus.QUEUED, index=True
    )
    trigger_source: Mapped[str] = mapped_column(String(64))
    """How this run was dispatched -- ``"cron"``, ``"interval"``,
    ``"calendar"``, ``"event:<name>"``, ``"dependency"``, or
    ``"manual"``."""

    priority_snapshot: Mapped[JobPriority] = mapped_column(String(32))
    """The job's own priority *at dispatch time* -- a later priority
    change on the job definition must not retroactively rewrite what an
    already-queued execution was actually dispatched at."""

    payload_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    duration_ms: Mapped[float | None] = mapped_column(Float, default=None)

    worker_id: Mapped[str | None] = mapped_column(String(128), default=None)
    node_id: Mapped[str | None] = mapped_column(String(128), default=None)
    exit_code: Mapped[int | None] = mapped_column(Integer, default=None)

    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    retries_used: Mapped[int] = mapped_column(Integer, default=0)

    error: Mapped[str | None] = mapped_column(Text, default=None)
    execution_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    artifacts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class JobExecutionLog(BaseModel):
    """``job_execution_logs`` -- one line of output from one execution."""

    __tablename__ = "job_execution_logs"
    __table_args__ = (Index("ix_job_execution_log_execution", "organization_id", "execution_id"),)

    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_executions.id", ondelete="CASCADE"), index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    level: Mapped[str] = mapped_column(String(16), default="info")
    message: Mapped[str] = mapped_column(Text)


__all__ = ["JobExecution", "JobExecutionLog"]
