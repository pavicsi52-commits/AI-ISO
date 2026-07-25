"""User notification preferences.

Per docs/025_Enterprise_Notification_Framework.md.txt "USER
PREFERENCES": Preferred Channels, Notification Categories, Quiet Hours,
Language, Timezone, Digest Frequency, Mute, Unsubscribe, Channel
Priority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.notifications.digest import DigestFrequency
from shared_core.notifications.exceptions import InvalidPreferenceError


@dataclass(slots=True)
class NotificationPreferences:
    """One user's notification preferences. Defaults are permissive (opted in, no quiet hours)."""

    user_id: str
    preferred_channels: list[NotificationChannel] = field(
        default_factory=lambda: [NotificationChannel.EMAIL, NotificationChannel.IN_APP]
    )
    muted_categories: set[NotificationType] = field(default_factory=set)
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    language: str = "en"
    timezone: str = "UTC"
    digest_frequency: DigestFrequency = DigestFrequency.NONE
    muted: bool = False
    unsubscribed_channels: set[NotificationChannel] = field(default_factory=set)
    channel_priority: list[NotificationChannel] = field(default_factory=list)

    def allows(self, *, channel: NotificationChannel, category: NotificationType) -> bool:
        """Whether this user currently accepts *category* notifications over *channel*.

        ``False`` if the user is fully muted, has unsubscribed from
        *channel* specifically, or has muted *category* specifically.
        """
        if self.muted:
            return False
        if channel in self.unsubscribed_channels:
            return False
        return category not in self.muted_categories

    def is_within_quiet_hours(self, moment: time) -> bool:
        """Whether *moment* (a time of day) falls within this user's configured quiet hours.

        Handles a window that wraps past midnight (e.g. 22:00-06:00).
        """
        if self.quiet_hours_start is None or self.quiet_hours_end is None:
            return False
        start, end = self.quiet_hours_start, self.quiet_hours_end
        if start <= end:
            return start <= moment < end
        return moment >= start or moment < end


class PreferencesStore:
    """An in-memory, per-user store of :class:`NotificationPreferences`."""

    def __init__(self) -> None:
        self._preferences: dict[str, NotificationPreferences] = {}

    def get(self, user_id: str) -> NotificationPreferences:
        """Return *user_id*'s preferences, creating a permissive default if none exist yet."""
        if user_id not in self._preferences:
            self._preferences[user_id] = NotificationPreferences(user_id=user_id)
        return self._preferences[user_id]

    def set(self, preferences: NotificationPreferences) -> None:
        """Replace the stored preferences for ``preferences.user_id``."""
        self._preferences[preferences.user_id] = preferences

    def mute(self, user_id: str) -> None:
        """Mute every notification for *user_id* ("Mute")."""
        self.get(user_id).muted = True

    def unmute(self, user_id: str) -> None:
        """Unmute *user_id*."""
        self.get(user_id).muted = False

    def unsubscribe(self, user_id: str, channel: NotificationChannel) -> None:
        """Unsubscribe *user_id* from *channel* ("Unsubscribe")."""
        self.get(user_id).unsubscribed_channels.add(channel)

    def set_channel_priority(self, user_id: str, channels: list[NotificationChannel]) -> None:
        """Set *user_id*'s preferred channel order ("Channel Priority").

        Raises:
            InvalidPreferenceError: If *channels* contains a duplicate.
        """
        if len(set(channels)) != len(channels):
            raise InvalidPreferenceError("Channel priority list must not contain duplicates.")
        self.get(user_id).channel_priority = list(channels)


__all__ = ["NotificationPreferences", "PreferencesStore"]
