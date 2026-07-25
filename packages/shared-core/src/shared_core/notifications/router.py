"""Notification routing.

Per docs/025_Enterprise_Notification_Framework.md.txt "USER
PREFERENCES": decides *which* channel(s) a notification should actually
go to (and whether it should wait for quiet hours to end), given a
user's preferences. Distinct from
:mod:`shared_core.notifications.dispatcher`, which does the actual
sending once the router has decided.
"""

from __future__ import annotations

from datetime import time

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.enums.notification_type import NotificationType
from shared_core.enums.priority import Priority
from shared_core.notifications.preferences import PreferencesStore

_QUIET_HOURS_OVERRIDE_PRIORITIES = frozenset({Priority.CRITICAL, Priority.HIGH})


class NotificationRouter:
    """Resolves which channel(s) a notification should be delivered over, per user preferences."""

    def __init__(self, preferences_store: PreferencesStore):
        self._preferences_store = preferences_store

    def resolve_channels(
        self,
        user_id: str,
        *,
        notification_type: NotificationType,
        requested_channel: NotificationChannel | None = None,
    ) -> list[NotificationChannel]:
        """Resolve the channel(s) to deliver to for *user_id*.

        If *requested_channel* is given, returns ``[requested_channel]``
        if the user's preferences allow it there, or ``[]`` if not (an
        explicit channel is never silently redirected elsewhere). With
        no *requested_channel*, returns every one of the user's
        ``preferred_channels`` that currently allows this
        *notification_type*, ordered by ``channel_priority`` if set.
        """
        preferences = self._preferences_store.get(user_id)
        candidates = (
            [requested_channel] if requested_channel is not None else preferences.preferred_channels
        )
        allowed = [
            channel
            for channel in candidates
            if preferences.allows(channel=channel, category=notification_type)
        ]
        if not preferences.channel_priority:
            return allowed
        priority_rank = {channel: rank for rank, channel in enumerate(preferences.channel_priority)}
        return sorted(allowed, key=lambda channel: priority_rank.get(channel, len(priority_rank)))

    def should_defer_for_quiet_hours(self, user_id: str, *, priority: Priority, now: time) -> bool:
        """Whether delivery should wait until the user's quiet hours end.

        Critical and High priority notifications always override quiet
        hours ("Priority affects delivery order" -- and, implicitly,
        whether it can interrupt quiet hours at all).
        """
        if priority in _QUIET_HOURS_OVERRIDE_PRIORITIES:
            return False
        preferences = self._preferences_store.get(user_id)
        return preferences.is_within_quiet_hours(now)


__all__ = ["NotificationRouter"]
