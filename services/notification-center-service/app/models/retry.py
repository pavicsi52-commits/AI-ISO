"""``notification_retry_queue`` and ``notification_dead_letters``.

Persisted equivalents of `shared_core.notifications.retry`'s in-memory
:class:`~shared_core.notifications.retry.DeadLetterStore` plus the
delayed-retry bookkeeping every prior service's own retry sweep already
established (docs/054's ``JobFailure.retry_at``/``retried``): a due
retry is found by querying ``next_retry_at <= now`` rather than holding
a live in-process timer per notification.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from shared_core.database.base import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import NotificationChannelKind


class NotificationRetryQueueEntry(BaseModel):
    """``notification_retry_queue`` -- one delivery's own pending retry."""

    __tablename__ = "notification_retry_queue"
    __table_args__ = (
        Index("ix_notification_retry_queue_due", "organization_id", "next_retry_at"),
        Index("ix_notification_retry_queue_delivery", "organization_id", "delivery_id"),
    )

    notification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), index=True
    )
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notification_deliveries.id", ondelete="CASCADE"), index=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer)
    next_retry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    """Set once the retry sweep has dispatched this entry's next
    attempt -- guards against dispatching it twice if a sweep tick
    overlaps its own previous one."""

    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class NotificationDeadLetter(BaseModel):
    """``notification_dead_letters`` -- one delivery that exhausted its retry policy."""

    __tablename__ = "notification_dead_letters"
    __table_args__ = (
        Index("ix_notification_dead_letter_notification", "organization_id", "notification_id"),
    )

    notification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), index=True
    )
    delivery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notification_deliveries.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[NotificationChannelKind] = mapped_column(String(32), index=True)
    attempts: Mapped[int] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    dead_lettered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    """Set by a manual retry ("Manual Retry") -- distinct from
    :attr:`NotificationRetryQueueEntry.resolved`, which tracks the
    *automatic* retry loop that led here."""

    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolution_note: Mapped[str | None] = mapped_column(Text, default=None)
    resolved_by: Mapped[str | None] = mapped_column(String(255), default=None)


__all__ = ["NotificationDeadLetter", "NotificationRetryQueueEntry"]
