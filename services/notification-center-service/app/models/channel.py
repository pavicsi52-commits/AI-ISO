"""``notification_channels`` -- one organization's own configuration for one channel.

Docs/055 "NOTIFICATION CHANNELS" lists eleven channels a deployment may
support; not every organization enables (or has credentials for) every
one. This table is the switch and its per-channel configuration
(webhook URLs, sender identities, provider settings) -- the channel
*implementation* itself lives in `shared_core.notifications`.
"""

from __future__ import annotations

from typing import Any

from shared_core.database.base import BaseModel
from sqlalchemy import JSON, Boolean, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.enums import NotificationChannelKind


class NotificationChannelConfig(BaseModel):
    """``notification_channels`` -- one organization's configuration for one channel."""

    __tablename__ = "notification_channels"
    __table_args__ = (
        UniqueConstraint("organization_id", "channel", name="uq_notification_channel_org_channel"),
    )

    channel: Mapped[NotificationChannelKind] = mapped_column(String(32), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    """Channel-specific settings -- e.g. a Slack incoming webhook URL, a
    custom webhook target and signing secret reference, or a sender
    identity. Never a credential in the clear; a real deployment stores
    only a reference into ``services/secrets-management-service``."""

    description: Mapped[str | None] = mapped_column(Text, default=None)


__all__ = ["NotificationChannelConfig"]
