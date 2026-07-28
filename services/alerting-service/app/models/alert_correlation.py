"""``alert_correlation`` table -- one edge linking two related alert
instances ("CORRELATION" "Support"). ``parent_alert_id`` is the
"primary"/root-cause alert; ``child_alert_id`` is the alert correlated
to it (e.g. a downstream service's own alert correlated to its
upstream dependency's outage via ``DEPENDENCY``/``TOPOLOGY``
correlation).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import CorrelationType


class AlertCorrelation(BaseModel):
    """One edge linking two related alert instances."""

    __tablename__ = "alert_correlation"

    parent_alert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alert_instances.id", ondelete="CASCADE"), index=True
    )
    child_alert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alert_instances.id", ondelete="CASCADE"), index=True
    )
    correlation_type: Mapped[CorrelationType] = mapped_column(String(24), index=True)
    correlated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["AlertCorrelation"]
