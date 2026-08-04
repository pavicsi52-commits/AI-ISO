"""``scheduled_jobs`` -- the job definition.

Deliberately carries no schedule-timing fields of its own beyond a
convenience ``last_run_at``/``next_run_at`` pair for cheap list/display
reads. The authoritative computed timing state lives in
:class:`~app.models.trigger.JobSchedule`, and the declarative rules that
feed it live in :class:`~app.models.trigger.JobTrigger` -- a job may have
more than one trigger (e.g. a cron trigger and an event trigger, either
of which fires it), and ``JobSchedule`` is the single materialized "when
is this job next due" row every trigger's own computation feeds into.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import JobPriority, JobType, ScheduledJobStatus


class ScheduledJob(BaseModel):
    """``scheduled_jobs`` -- one job an organization has registered."""

    __tablename__ = "scheduled_jobs"
    __table_args__ = (
        Index("ix_scheduled_job_org_status", "organization_id", "status"),
        Index("ix_scheduled_job_org_type", "organization_id", "job_type"),
        Index("ix_scheduled_job_org_priority", "organization_id", "priority"),
    )

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)

    job_type: Mapped[JobType] = mapped_column(String(32), default=JobType.CUSTOM_JOB, index=True)
    status: Mapped[ScheduledJobStatus] = mapped_column(
        String(32), default=ScheduledJobStatus.REGISTERED, index=True
    )
    priority: Mapped[JobPriority] = mapped_column(
        String(32), default=JobPriority.NORMAL, index=True
    )

    owner_id: Mapped[str | None] = mapped_column(String(255), default=None)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")

    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    """Opaque data handed to whichever platform service actually
    performs the work this job dispatches -- this service does not
    interpret it."""

    job_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)

    timeout_seconds: Mapped[float | None] = mapped_column(Float, default=None)

    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    """Denormalised from :class:`~app.models.trigger.JobSchedule` for
    cheap list-view reads. ``JobSchedule`` remains the value a sweep
    actually polls against."""

    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    run_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)


__all__ = ["ScheduledJob"]
