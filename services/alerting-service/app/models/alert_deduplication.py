"""``alert_deduplication`` table -- one fingerprint registry entry
("DEDUPLICATION" "Support": Duplicate Detection, Fingerprinting, Hash
Matching, Event Consolidation). Maps a computed ``fingerprint`` to the
"primary" :class:`~app.models.alert_instance.AlertInstance` every
subsequent duplicate occurrence consolidates into, tracking how many
times it has recurred and its own first/last occurrence for "Time
Window Deduplication".
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DeduplicationStrategy


class AlertDeduplication(BaseModel):
    """One fingerprint registry entry consolidating repeated alert occurrences."""

    __tablename__ = "alert_deduplication"

    fingerprint: Mapped[str] = mapped_column(String(128), index=True, unique=True)
    primary_alert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alert_instances.id", ondelete="CASCADE"), index=True
    )
    strategy: Mapped[DeduplicationStrategy] = mapped_column(String(16), index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["AlertDeduplication"]
