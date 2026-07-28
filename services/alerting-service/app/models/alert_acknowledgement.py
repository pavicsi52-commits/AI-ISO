"""``alert_acknowledgements`` table -- one acknowledgement record
("ACKNOWLEDGEMENT" "Support": Manual/Automatic Acknowledgement,
Ownership, Assignment, Comments, Resolution Notes). ``acknowledged_by``
is nullable -- an ``AUTOMATIC`` acknowledgement has no human actor.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AcknowledgementType


class AlertAcknowledgement(BaseModel):
    """One acknowledgement record for an alert instance."""

    __tablename__ = "alert_acknowledgements"

    alert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alert_instances.id", ondelete="CASCADE"), index=True
    )
    acknowledgement_type: Mapped[AcknowledgementType] = mapped_column(
        String(16), default=AcknowledgementType.MANUAL
    )
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    comment: Mapped[str | None] = mapped_column(Text, default=None)
    resolution_notes: Mapped[str | None] = mapped_column(Text, default=None)
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


__all__ = ["AlertAcknowledgement"]
