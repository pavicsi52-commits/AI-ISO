"""Response schema for an alert's own notification delivery attempts
("NOTIFICATIONS" "Delivery Tracking").
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import AlertRouteChannel, NotificationDeliveryStatus


class AlertNotificationResponse(BaseModel):
    """One notification delivery attempt for an alert."""

    id: UUID
    alert_id: UUID
    route_id: UUID | None
    channel: AlertRouteChannel
    status: NotificationDeliveryStatus
    retry_count: int
    error_message: str | None
    sent_at: datetime | None


__all__ = ["AlertNotificationResponse"]
