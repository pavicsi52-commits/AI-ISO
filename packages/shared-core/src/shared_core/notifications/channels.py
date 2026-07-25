"""Notification message model and channel interface.

Per docs/025_Enterprise_Notification_Framework.md.txt "MESSAGE MODEL"
and "CHANNELS": "Every channel shall implement the same interface" --
:class:`Channel`, a single ``async def send(message) -> DeliveryResult``
every concrete channel (:mod:`shared_core.notifications.email`, ``.sms``,
``.push``, ``.in_app``, ``.slack``, ``.teams``, ``.discord``, ``.webhook``)
implements identically.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.enums.priority import Priority
from shared_core.notifications.attachments import Attachment
from shared_core.notifications.delivery import DeliveryResult, DeliveryStatus
from shared_core.notifications.exceptions import ChannelUnavailableError


@dataclass(slots=True)
class NotificationMessage:
    """Every field docs/025 "MESSAGE MODEL" requires. Mutable: status/timestamps update in place."""

    notification_id: str
    channel: NotificationChannel
    notification_type: NotificationType
    priority: Priority
    body: str
    organization_id: str | None = None
    project_id: str | None = None
    user_id: str | None = None
    subject: str | None = None
    title: str | None = None
    template: str | None = None
    variables: dict[str, Any] = field(default_factory=dict)
    attachments: list[Attachment] = field(default_factory=list)
    status: DeliveryStatus = DeliveryStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    sent_at: datetime | None = None
    delivered_at: datetime | None = None
    read_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def new_notification_id() -> str:
    """Generate a new, unique notification ID."""
    return str(uuid.uuid4())


def build_notification(
    *,
    channel: NotificationChannel,
    notification_type: NotificationType,
    body: str,
    priority: Priority = Priority.NORMAL,
    **fields: Any,
) -> NotificationMessage:
    """Build a :class:`NotificationMessage` with a freshly generated ID."""
    return NotificationMessage(
        notification_id=new_notification_id(),
        channel=channel,
        notification_type=notification_type,
        priority=priority,
        body=body,
        **fields,
    )


WebhookUrlResolver = Callable[[NotificationMessage], str]
"""Resolves the outbound webhook URL for a message -- shared by every webhook-shaped
channel (:mod:`shared_core.notifications.slack`, ``.teams``, ``.discord``, ``.webhook``)."""


@runtime_checkable
class Channel(Protocol):
    """The interface every delivery channel implements identically."""

    channel_type: NotificationChannel

    async def send(self, message: NotificationMessage) -> DeliveryResult:
        """Deliver *message*, returning the outcome. Never raises for a normal delivery failure --
        a failed send is a ``DeliveryResult(status=DeliveryStatus.FAILED, ...)``, not an exception.
        """
        ...


class ChannelRegistry:
    """Registry of configured channels, by :class:`NotificationChannel`."""

    def __init__(self) -> None:
        self._channels: dict[NotificationChannel, Channel] = {}

    def register(self, channel: Channel) -> None:
        """Register *channel* under its own ``channel_type``."""
        self._channels[channel.channel_type] = channel

    def get(self, channel_type: NotificationChannel) -> Channel:
        """Return the registered channel for *channel_type*.

        Raises:
            ChannelUnavailableError: If no channel is registered for *channel_type*.
        """
        channel = self._channels.get(channel_type)
        if channel is None:
            raise ChannelUnavailableError(f"No channel registered for {channel_type.value!r}.")
        return channel

    def is_registered(self, channel_type: NotificationChannel) -> bool:
        """Whether a channel is registered for *channel_type*."""
        return channel_type in self._channels

    def registered_channels(self) -> list[NotificationChannel]:
        """Every currently registered channel type."""
        return list(self._channels)


__all__ = [
    "Channel",
    "ChannelRegistry",
    "NotificationMessage",
    "WebhookUrlResolver",
    "build_notification",
    "new_notification_id",
]
