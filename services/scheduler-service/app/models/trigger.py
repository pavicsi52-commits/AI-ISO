"""``job_triggers`` and ``job_schedules``.

A job may carry more than one trigger -- a cron trigger and an event
trigger both firing the same job is a real, common configuration, not
an edge case. ``JobSchedule`` is the single materialized row every one
of a job's triggers' own next-due computation feeds into: the sweep
worker polls ``job_schedules.next_run_at`` directly rather than
re-evaluating every trigger on every tick.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import CalendarRuleKind, ScheduleType


class JobTrigger(BaseModel):
    """``job_triggers`` -- one declarative rule that can fire a job.

    Exactly the fields its own ``trigger_type`` needs are meaningfully
    set; the rest stay ``None`` -- the same "only what this type needs"
    shape as ``shared_core.scheduler.schedule.Schedule``, persisted.
    """

    __tablename__ = "job_triggers"
    __table_args__ = (Index("ix_job_trigger_job", "organization_id", "job_id"),)

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scheduled_jobs.id", ondelete="CASCADE"), index=True
    )
    trigger_type: Mapped[ScheduleType] = mapped_column(String(32), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    cron_expression: Mapped[str | None] = mapped_column(String(128), default=None)
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    interval_seconds: Mapped[float | None] = mapped_column(Float, default=None)
    calendar_rule: Mapped[CalendarRuleKind | None] = mapped_column(String(32), default=None)
    calendar_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    """Rule-specific detail a bare ``calendar_rule`` band can't carry --
    e.g. which weekday(s) for ``WEEKLY``, or which day-of-month for
    ``MONTHLY``."""

    event_name: Mapped[str | None] = mapped_column(String(255), default=None)
    """The domain event name this trigger fires on, for ``EVENT_DRIVEN``."""

    description: Mapped[str | None] = mapped_column(Text, default=None)


class JobSchedule(BaseModel):
    """``job_schedules`` -- one job's own materialized next-due state."""

    __tablename__ = "job_schedules"
    __table_args__ = (
        UniqueConstraint("organization_id", "job_id", name="uq_job_schedule_job"),
        Index("ix_job_schedule_next_run", "organization_id", "next_run_at"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scheduled_jobs.id", ondelete="CASCADE"), index=True
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None, index=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    pause_reason: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["JobSchedule", "JobTrigger"]
