"""``discovery_results`` table -- the raw outcome of one protocol probe
against one target, within one job.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DiscoveryResultStatus, ProtocolType


class DiscoveryResult(BaseModel):
    """One protocol probe's raw outcome."""

    __tablename__ = "discovery_results"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_jobs.id", ondelete="CASCADE"), index=True
    )
    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_targets.id", ondelete="CASCADE"), index=True
    )
    protocol: Mapped[ProtocolType] = mapped_column(String(16), index=True)
    status: Mapped[DiscoveryResultStatus] = mapped_column(String(16), index=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, default=None)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(String(2048), default=None)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["DiscoveryResult"]
