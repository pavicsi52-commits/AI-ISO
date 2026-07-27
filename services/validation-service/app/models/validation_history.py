"""``validation_history`` table -- one lightweight, per-target
historical snapshot row, distinct from the full
``validation_executions``/``validation_results`` rows so trend queries
("Asset Health Trends") can scan a small, purpose-built table instead
of re-aggregating the full result set on every read.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import ValidationExecutionStatus


class ValidationHistory(BaseModel):
    """One lightweight, per-target historical validation snapshot."""

    __tablename__ = "validation_history"

    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("validation_targets.id", ondelete="CASCADE"), index=True
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("validation_executions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[ValidationExecutionStatus] = mapped_column(String(16), index=True)
    score: Mapped[float | None] = mapped_column(Float, default=None)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


__all__ = ["ValidationHistory"]
