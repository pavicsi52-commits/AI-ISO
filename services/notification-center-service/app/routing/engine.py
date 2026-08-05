"""Pure channel-routing decisions.

`shared_core.notifications.router.NotificationRouter` and
`shared_core.notifications.preferences.NotificationPreferences` already
implement this exact algorithm -- "allow" checks, quiet-hours windows,
channel-priority ordering -- but keyed to `shared_core`'s own eight-member
:class:`~shared_core.enums.notification_channel.NotificationChannel` and
fifteen-member :class:`~shared_core.enums.notification_type
.NotificationType`. This service's own vocabulary is deliberately richer
(docs/055 "NOTIFICATION CHANNELS"/"NOTIFICATION TYPES" name more values
than `shared_core` models -- see :mod:`app.models.enums`), and round-
tripping every one of these small, pure checks through a lossy
translation into the narrower vocabulary and back would be more code, not
less. This module reimplements the same three checks natively against
this service's own richer enums; the parts that are *not* small and pure
-- actual rendering, actual channel I/O, actual backoff math -- still
delegate to `shared_core` directly (see :mod:`app.rendering.engine`,
:mod:`app.retries.engine`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from app.models.enums import NotificationCategory, NotificationChannelKind, NotificationPriority

_QUIET_HOURS_OVERRIDE_PRIORITIES = frozenset(
    {NotificationPriority.CRITICAL, NotificationPriority.HIGH}
)


@dataclass(frozen=True, slots=True)
class PreferenceSnapshot:
    """The fields of one stored :class:`~app.models.preference.NotificationPreference`
    row a routing decision actually needs, decoupled from the ORM row so
    this module stays a pure function of its inputs."""

    user_id: str
    preferred_channels: tuple[NotificationChannelKind, ...] = ()
    muted_categories: frozenset[NotificationCategory] = frozenset()
    unsubscribed_channels: frozenset[NotificationChannelKind] = frozenset()
    channel_priority: tuple[NotificationChannelKind, ...] = ()
    muted: bool = False
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None


def allows(
    preferences: PreferenceSnapshot,
    *,
    channel: NotificationChannelKind,
    category: NotificationCategory,
) -> bool:
    """Whether *preferences*' owner currently accepts *category* over *channel*.

    ``False`` if fully muted, unsubscribed from *channel* specifically,
    or *category* is muted specifically -- the same three rules as
    `shared_core.notifications.preferences.NotificationPreferences.allows`.
    """
    if preferences.muted:
        return False
    if channel in preferences.unsubscribed_channels:
        return False
    return category not in preferences.muted_categories


def is_within_quiet_hours(preferences: PreferenceSnapshot, moment: time) -> bool:
    """Whether *moment* falls within *preferences*' configured quiet hours.

    Handles a window that wraps past midnight (e.g. 22:00-06:00).
    """
    start, end = preferences.quiet_hours_start, preferences.quiet_hours_end
    if start is None or end is None:
        return False
    if start <= end:
        return start <= moment < end
    return moment >= start or moment < end


def should_defer_for_quiet_hours(
    preferences: PreferenceSnapshot, *, priority: NotificationPriority, now: time
) -> bool:
    """Whether delivery should wait until *preferences*' quiet hours end.

    Critical and High priority notifications always override quiet
    hours ("Priority Overrides").
    """
    if priority in _QUIET_HOURS_OVERRIDE_PRIORITIES:
        return False
    return is_within_quiet_hours(preferences, now)


def resolve_channels(
    preferences: PreferenceSnapshot,
    *,
    category: NotificationCategory,
    requested_channel: NotificationChannelKind | None = None,
) -> list[NotificationChannelKind]:
    """Resolve which channel(s) to deliver over.

    With an explicit *requested_channel*, returns ``[requested_channel]``
    if preferences allow it there, or ``[]`` if not -- an explicit
    channel is never silently redirected elsewhere. With none, returns
    every one of the owner's ``preferred_channels`` that currently
    allows *category*, ordered by ``channel_priority`` if set.
    """
    candidates: list[NotificationChannelKind] = (
        [requested_channel]
        if requested_channel is not None
        else list(preferences.preferred_channels)
    )
    allowed = [
        channel for channel in candidates if allows(preferences, channel=channel, category=category)
    ]
    if not preferences.channel_priority:
        return allowed
    priority_rank = {channel: rank for rank, channel in enumerate(preferences.channel_priority)}
    return sorted(allowed, key=lambda channel: priority_rank.get(channel, len(priority_rank)))


__all__ = [
    "PreferenceSnapshot",
    "allows",
    "is_within_quiet_hours",
    "resolve_channels",
    "should_defer_for_quiet_hours",
]
