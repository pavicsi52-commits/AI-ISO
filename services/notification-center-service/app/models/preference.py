"""``notification_preferences`` -- one user's own delivery preferences.

The persisted mirror of `shared_core.notifications.preferences
.NotificationPreferences`, per-organization (a user active in more than
one organization may reasonably want different quiet hours or muted
categories in each). :mod:`app.routing.engine` converts a row here into
the `shared_core` dataclass the router actually reasons over.
"""

from __future__ import annotations

from datetime import time
from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import DigestFrequency


class NotificationPreference(BaseModel):
    """``notification_preferences`` -- one user's own settings within one organization."""

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_notification_preference_user"),
    )

    user_id: Mapped[str] = mapped_column(String(255), index=True)

    preferred_channels: Mapped[list[str]] = mapped_column(JSON, default=list)
    muted_categories: Mapped[list[str]] = mapped_column(JSON, default=list)
    unsubscribed_channels: Mapped[list[str]] = mapped_column(JSON, default=list)
    channel_priority: Mapped[list[str]] = mapped_column(JSON, default=list)
    device_tokens: Mapped[list[str]] = mapped_column(JSON, default=list)
    """Registered mobile/browser push endpoints ("Device Preferences")."""

    quiet_hours_start: Mapped[time | None] = mapped_column(Time, default=None)
    quiet_hours_end: Mapped[time | None] = mapped_column(Time, default=None)

    language: Mapped[str] = mapped_column(String(16), default="en")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    digest_frequency: Mapped[DigestFrequency] = mapped_column(
        String(16), default=DigestFrequency.NONE
    )
    muted: Mapped[bool] = mapped_column(Boolean, default=False)
    """"Do Not Disturb" -- every notification is suppressed regardless of
    channel or category until unmuted."""

    priority_overrides: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    """Per-category priority floor overrides ("Priority Overrides") --
    e.g. force every ``approval_request`` to be treated as at least
    ``HIGH`` for this user, keyed by :class:`~app.models.enums
    .NotificationCategory` value."""


__all__ = ["NotificationPreference"]
