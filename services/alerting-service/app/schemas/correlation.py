"""Response schema for an alert's own correlation edges."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import CorrelationType


class AlertCorrelationResponse(BaseModel):
    """One edge linking two related alerts."""

    id: UUID
    parent_alert_id: UUID
    child_alert_id: UUID
    correlation_type: CorrelationType
    correlated_at: datetime


__all__ = ["AlertCorrelationResponse"]
