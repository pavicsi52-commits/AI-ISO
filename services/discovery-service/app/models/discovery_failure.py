"""``discovery_failures`` table -- one target's failed probe within a job."""

from __future__ import annotations

import uuid

from shared_core.database.base import BaseModel
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import FailureReason, ProtocolType


class DiscoveryFailure(BaseModel):
    """One failed discovery probe."""

    __tablename__ = "discovery_failures"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_jobs.id", ondelete="CASCADE"), index=True
    )
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("discovery_targets.id", ondelete="SET NULL"), default=None
    )
    protocol: Mapped[ProtocolType] = mapped_column(String(16), index=True)
    failure_reason: Mapped[FailureReason] = mapped_column(
        String(24), default=FailureReason.UNKNOWN, index=True
    )
    error_detail: Mapped[str | None] = mapped_column(String(2048), default=None)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)


__all__ = ["DiscoveryFailure"]
