"""``alert_notifications`` table -- one notification delivery attempt
("NOTIFICATIONS" "Retry", "Delivery Tracking"). ``route_id`` is
nullable -- a notification may be triggered by an escalation level
with no pre-configured :class:`~app.models.alert_route.AlertRoute` row
of its own (e.g. a one-off manager escalation).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import AlertRouteChannel, NotificationDeliveryStatus


class AlertNotification(BaseModel):
    """One notification delivery attempt for an alert."""

    __tablename__ = "alert_notifications"

    alert_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("alert_instances.id", ondelete="CASCADE"), index=True
    )
    route_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("alert_routes.id", ondelete="SET NULL"), default=None, index=True
    )
    channel: Mapped[AlertRouteChannel] = mapped_column(String(16), index=True)
    status: Mapped[NotificationDeliveryStatus] = mapped_column(
        String(16), default=NotificationDeliveryStatus.PENDING, index=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["AlertNotification"]
