"""Notification digest.

Per docs/025_Enterprise_Notification_Framework.md.txt "DIGEST": Hourly,
Daily, Weekly, Monthly, Summary Generation, Duplicate Removal, Grouping.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from shared_core.notifications.channels import NotificationMessage
from shared_core.notifications.constants import DEFAULT_DIGEST_MAX_ITEMS


class DigestFrequency(StrEnum):
    """Per docs/025 "DIGEST": Hourly/Daily/Weekly/Monthly. ``NONE`` means "no digest, immediate"."""

    NONE = "none"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


@dataclass(frozen=True, slots=True)
class DigestGroup:
    """One category's notifications within a digest, deduplicated."""

    notification_type: str
    messages: tuple[NotificationMessage, ...]


@dataclass(frozen=True, slots=True)
class Digest:
    """A batch of grouped, deduplicated notifications for one recipient."""

    user_id: str
    groups: tuple[DigestGroup, ...]

    @property
    def total_count(self) -> int:
        """Total notifications across every group."""
        return sum(len(group.messages) for group in self.groups)


def _dedupe_key(message: NotificationMessage) -> tuple[str, str, str]:
    """Two notifications are duplicates if they share type, subject, and body."""
    return message.notification_type.value, message.subject or "", message.body


def build_digest(
    user_id: str, messages: list[NotificationMessage], *, max_items: int = DEFAULT_DIGEST_MAX_ITEMS
) -> Digest:
    """Group *messages* by type, removing duplicates, capped at *max_items* total.

    ("Grouping", "Duplicate Removal", "Summary Generation" -- a
    :class:`Digest` *is* the summary; formatting it into a rendered
    notification body is :mod:`shared_core.notifications.renderer`'s job.)
    """
    seen: set[tuple[str, str, str]] = set()
    deduplicated: list[NotificationMessage] = []
    for message in messages:
        key = _dedupe_key(message)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(message)
        if len(deduplicated) >= max_items:
            break

    grouped: dict[str, list[NotificationMessage]] = defaultdict(list)
    for message in deduplicated:
        grouped[message.notification_type.value].append(message)

    groups = tuple(
        DigestGroup(notification_type=notification_type, messages=tuple(group_messages))
        for notification_type, group_messages in grouped.items()
    )
    return Digest(user_id=user_id, groups=groups)


__all__ = ["Digest", "DigestFrequency", "DigestGroup", "build_digest"]
