"""``discovery_schedules`` table -- when a profile runs automatically.

Per docs/037 "SCHEDULING": "Integrate with Prompt 026." This row is the
discovery-domain configuration (which profile, what cadence, retry/
priority/concurrency policy); the actual cron/interval computation and
distributed execution is delegated to
``shared_core.scheduler`` at registration time
(``app/scheduling/registrar.py``), not reimplemented here.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ScheduleType


class DiscoverySchedule(BaseModel):
    """One recurring or one-time discovery schedule."""

    __tablename__ = "discovery_schedules"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_profiles.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    schedule_type: Mapped[ScheduleType] = mapped_column(String(16), default=ScheduleType.RECURRING)
    cron_expression: Mapped[str | None] = mapped_column(String(128), default=None)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, default=None)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    """Whether this schedule should currently fire -- deliberately a
    distinct column from :class:`~shared_core.database.base.BaseModel`'s
    own ``is_active`` (soft-delete flag): a schedule paused by setting
    this ``False`` must stay visible/queryable, not disappear from every
    ``_base_select()``-filtered lookup the way an actually-deleted row
    would. A real bug caught live during testing -- this field was
    originally (wrongly) named ``is_active`` too, which silently soft-
    deleted a schedule the moment a caller paused it.
    """
    maintenance_window: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    retry_policy: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    priority: Mapped[int] = mapped_column(Integer, default=5)
    concurrency_limit: Mapped[int] = mapped_column(Integer, default=1)


__all__ = ["DiscoverySchedule"]
