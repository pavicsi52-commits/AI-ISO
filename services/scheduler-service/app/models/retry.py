"""``job_retry_policies`` -- how a job's failed executions get retried."""

from __future__ import annotations

import uuid
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import RetryType


class JobRetryPolicy(BaseModel):
    """``job_retry_policies`` -- one job's own retry configuration."""

    __tablename__ = "job_retry_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", "job_id", name="uq_job_retry_policy_job"),
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scheduled_jobs.id", ondelete="CASCADE"), index=True
    )
    retry_type: Mapped[RetryType] = mapped_column(String(32), default=RetryType.EXPONENTIAL_BACKOFF)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    base_delay_seconds: Mapped[float] = mapped_column(Float, default=5.0)
    max_delay_seconds: Mapped[float] = mapped_column(Float, default=300.0)
    retry_conditions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    """E.g. ``{"exit_codes": [1, 2], "error_patterns": ["Timeout"]}`` --
    empty means "retry on any failure," the safe default."""

    dead_letter_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


__all__ = ["JobRetryPolicy"]
