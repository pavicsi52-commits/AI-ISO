"""``notification_announcements`` and ``notification_broadcasts``.

Distinct concepts sharing a table pair, per docs/055 "ANNOUNCEMENTS":
:class:`NotificationAnnouncement` is a persistent, pinnable, expiring
content object (what the in-app notification center's own "Announcements"
tab lists); :class:`NotificationBroadcast` is one *fan-out operation* --
either publishing an announcement to its audience, or an ad-hoc
``POST /notifications/broadcast`` with no announcement behind it at all.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import (
    AnnouncementScope,
    AnnouncementStatus,
    BroadcastStatus,
    NotificationCategory,
    NotificationChannelKind,
    NotificationPriority,
)


class NotificationAnnouncement(BaseModel):
    """``notification_announcements`` -- one persistent, targetable announcement."""

    __tablename__ = "notification_announcements"
    __table_args__ = (
        Index("ix_notification_announcement_org_status", "organization_id", "status"),
        Index("ix_notification_announcement_org_expires", "organization_id", "expires_at"),
    )

    scope: Mapped[AnnouncementScope] = mapped_column(String(32), index=True)
    status: Mapped[AnnouncementStatus] = mapped_column(
        String(16), default=AnnouncementStatus.DRAFT, index=True
    )

    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False)

    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    audience: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    """Targeting spec (docs/055 "TARGETING"): keys among ``users``,
    ``teams``, ``roles``, ``organizations``, ``projects``, ``groups``,
    ``regions``, ``environments``, ``custom``, each a list of
    identifiers. An empty dict targets every member of :attr:`scope`."""


class NotificationBroadcast(BaseModel):
    """``notification_broadcasts`` -- one fan-out send operation."""

    __tablename__ = "notification_broadcasts"
    __table_args__ = (
        Index("ix_notification_broadcast_org_status", "organization_id", "status"),
        Index("ix_notification_broadcast_announcement", "organization_id", "announcement_id"),
    )

    announcement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("notification_announcements.id", ondelete="SET NULL"), default=None, index=True
    )
    topic: Mapped[str | None] = mapped_column(String(255), default=None)
    """The subscription topic fanned out to, when this broadcast targets
    subscribers rather than an announcement's own audience spec."""

    category: Mapped[NotificationCategory] = mapped_column(
        String(32), default=NotificationCategory.SYSTEM_ANNOUNCEMENT
    )
    priority: Mapped[NotificationPriority] = mapped_column(
        String(32), default=NotificationPriority.NORMAL
    )
    channel: Mapped[NotificationChannelKind | None] = mapped_column(String(32), default=None)
    """An explicit channel override, or ``None`` to route each recipient
    through their own preferences."""

    subject: Mapped[str | None] = mapped_column(String(255), default=None)
    body: Mapped[str] = mapped_column(Text)

    status: Mapped[BroadcastStatus] = mapped_column(
        String(16), default=BroadcastStatus.PENDING, index=True
    )
    total_recipients: Mapped[int] = mapped_column(Integer, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)

    initiated_by: Mapped[str | None] = mapped_column(String(255), default=None)
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


__all__ = ["NotificationAnnouncement", "NotificationBroadcast"]
