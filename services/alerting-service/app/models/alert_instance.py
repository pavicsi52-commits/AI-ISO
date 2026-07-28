"""``alert_instances`` table -- one fired alert, this service's own
central entity. ``rule_id`` is nullable -- ``POST /alerts`` allows a
caller to raise an alert directly (docs/045's own literal REST list),
not only through the rule engine. ``fingerprint`` backs "Fingerprinting"/
"Hash Matching" deduplication lookups; ``source_reference`` carries
whatever identifiers the originating service's own event included
(e.g. ``{"target_id": "..."}`` from Monitoring) without this service
needing a foreign key into every other service's own schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from shared_core.enums.severity import Severity
from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AlertSource, AlertStatus


class AlertInstance(BaseModel):
    """One fired alert."""

    __tablename__ = "alert_instances"

    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="SET NULL"), default=None, index=True
    )
    source: Mapped[AlertSource] = mapped_column(String(32), index=True)
    severity: Mapped[Severity] = mapped_column(String(16), index=True)
    status: Mapped[AlertStatus] = mapped_column(String(16), default=AlertStatus.NEW, index=True)
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(128), index=True)
    source_reference: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(default=None)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["AlertInstance"]
