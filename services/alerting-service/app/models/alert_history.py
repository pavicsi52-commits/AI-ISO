"""``alert_history`` table -- one status-transition event for an alert
instance's own lifecycle ("ALERT STATUS", "Audit History"). Distinct
from the org-wide ``alert_audit`` (administrative/configuration
changes) -- this is a per-alert timeline purpose-built for a fast
"show me this alert's own history" read.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AlertStatus


class AlertHistory(BaseModel):
    """One status-transition event for an alert instance."""

    __tablename__ = "alert_history"

    alert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alert_instances.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[AlertStatus | None] = mapped_column(String(16), default=None)
    to_status: Mapped[AlertStatus] = mapped_column(String(16), index=True)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["AlertHistory"]
