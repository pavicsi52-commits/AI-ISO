"""``notifications`` -- one logical notification addressed to one recipient.

The canonical record of "something worth telling this user about"
happened. A broadcast fans out into one ``Notification`` row per
recipient (see :class:`~app.models.announcement.NotificationBroadcast`),
sharing a ``correlation_id`` rather than existing as a single
multi-recipient row -- every downstream concept (read/unread, per-channel
delivery, retry) is inherently per-recipient, so a single shared row
would need its own recipient-keyed sub-state anyway.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import NotificationCategory, NotificationPriority, NotificationStatus


class Notification(BaseModel):
    """``notifications`` -- one notification addressed to one recipient."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notification_org_user_status", "organization_id", "user_id", "status"),
        Index("ix_notification_org_status", "organization_id", "status"),
        Index("ix_notification_org_correlation", "organization_id", "correlation_id"),
    )

    user_id: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[NotificationCategory] = mapped_column(
        String(32), default=NotificationCategory.INFORMATION, index=True
    )
    priority: Mapped[NotificationPriority] = mapped_column(
        String(32), default=NotificationPriority.NORMAL, index=True
    )
    status: Mapped[NotificationStatus] = mapped_column(
        String(32), default=NotificationStatus.CREATED, index=True
    )

    subject: Mapped[str | None] = mapped_column(String(255), default=None)
    body: Mapped[str] = mapped_column(Text)

    template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("notification_templates.id", ondelete="SET NULL"), default=None, index=True
    )
    template_variables: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    source_service: Mapped[str] = mapped_column(String(128), index=True)
    """Which docs/055 "EVENT SOURCES" platform service originated this
    notification, e.g. ``"scheduler-service"``."""

    source_event_type: Mapped[str | None] = mapped_column(String(128), default=None)
    correlation_id: Mapped[str | None] = mapped_column(String(64), default=None)
    """Groups every recipient's own row from the same broadcast or
    fan-out together -- not a foreign key, since it may correlate rows
    with no single owning broadcast (e.g. an event-driven fan-out to a
    role's every member)."""

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    notification_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)


__all__ = ["Notification"]
