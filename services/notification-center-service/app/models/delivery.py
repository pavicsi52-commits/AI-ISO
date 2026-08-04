"""``notification_deliveries`` and ``notification_delivery_attempts``.

One :class:`~app.models.notification.Notification` fans out into one
``NotificationDelivery`` per channel it is actually sent over (a user
with both email and Slack in their preferred channels gets two delivery
rows from one notification); each delivery's own retry loop is recorded
attempt-by-attempt in :class:`NotificationDeliveryAttempt`, mirroring
`shared_core.notifications.history.HistoryStore`'s in-memory shape,
persisted.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import NotificationChannelKind, NotificationStatus


class NotificationDelivery(BaseModel):
    """``notification_deliveries`` -- one channel's own attempt to reach one recipient."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        Index("ix_notification_delivery_notification", "organization_id", "notification_id"),
        Index("ix_notification_delivery_org_status", "organization_id", "status"),
        Index("ix_notification_delivery_org_channel", "organization_id", "channel"),
    )

    notification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[NotificationChannelKind] = mapped_column(String(32), index=True)
    status: Mapped[NotificationStatus] = mapped_column(
        String(32), default=NotificationStatus.QUEUED, index=True
    )

    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    attempts_used: Mapped[int] = mapped_column(Integer, default=0)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    latency_ms: Mapped[float | None] = mapped_column(Float, default=None)
    response_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class NotificationDeliveryAttempt(BaseModel):
    """``notification_delivery_attempts`` -- one individual send attempt."""

    __tablename__ = "notification_delivery_attempts"
    __table_args__ = (
        Index("ix_notification_delivery_attempt_delivery", "organization_id", "delivery_id"),
    )

    delivery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notification_deliveries.id", ondelete="CASCADE"), index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[NotificationStatus] = mapped_column(String(32))
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    latency_ms: Mapped[float | None] = mapped_column(Float, default=None)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), default=None)


__all__ = ["NotificationDelivery", "NotificationDeliveryAttempt"]
