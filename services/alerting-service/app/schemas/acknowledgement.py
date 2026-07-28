"""Response schema for an alert's own acknowledgement records."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import AcknowledgementType


class AlertAcknowledgementResponse(BaseModel):
    """One acknowledgement record for an alert."""

    id: UUID
    alert_id: UUID
    acknowledgement_type: AcknowledgementType
    acknowledged_by: UUID | None
    comment: str | None
    resolution_notes: str | None
    acknowledged_at: datetime


__all__ = ["AlertAcknowledgementResponse"]
