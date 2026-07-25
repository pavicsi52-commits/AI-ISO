"""In-app notification channel and store.

Per docs/025_Enterprise_Notification_Framework.md.txt "IN-APP
NOTIFICATIONS": Unread, Read, Archived, Pinned, Categories, Search,
Filtering, Pagination.

Purely in-process, the same "no business/persistence tables" stance as
every prior framework's own state ("DO NOT IMPLEMENT": Business Logic)
-- a real service persisting in-app notifications across restarts
provides its own store implementing this same shape (or simply
subclasses :class:`InAppNotificationStore` and overrides its methods).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from shared_core.enums.notification_channel import NotificationChannel
from shared_core.notifications.channels import NotificationMessage
from shared_core.notifications.constants import DEFAULT_IN_APP_PAGE_SIZE
from shared_core.notifications.delivery import DeliveryResult, DeliveryStatus, build_delivery_result


class InAppStatus(StrEnum):
    """Per docs/025 "IN-APP NOTIFICATIONS": Unread, Read, Archived."""

    UNREAD = "unread"
    READ = "read"
    ARCHIVED = "archived"


@dataclass(slots=True)
class InAppNotificationRecord:
    """One in-app notification, tracked separately from delivery status."""

    message: NotificationMessage
    in_app_status: InAppStatus = InAppStatus.UNREAD
    pinned: bool = False
    category: str | None = None


class InAppNotificationStore:
    """An in-memory, per-user store of in-app notifications."""

    def __init__(self) -> None:
        self._records: dict[str, list[InAppNotificationRecord]] = {}

    def add(
        self, message: NotificationMessage, *, category: str | None = None
    ) -> InAppNotificationRecord:
        """Store *message* as a new in-app notification for its ``user_id``."""
        user_id = message.user_id or ""
        record = InAppNotificationRecord(message=message, category=category)
        self._records.setdefault(user_id, []).append(record)
        return record

    def _find(self, user_id: str, notification_id: str) -> InAppNotificationRecord | None:
        for record in self._records.get(user_id, []):
            if record.message.notification_id == notification_id:
                return record
        return None

    def mark_read(self, user_id: str, notification_id: str) -> None:
        """Mark one notification as read ("Read")."""
        record = self._find(user_id, notification_id)
        if record is not None:
            record.in_app_status = InAppStatus.READ

    def mark_unread(self, user_id: str, notification_id: str) -> None:
        """Mark one notification as unread ("Unread")."""
        record = self._find(user_id, notification_id)
        if record is not None:
            record.in_app_status = InAppStatus.UNREAD

    def archive(self, user_id: str, notification_id: str) -> None:
        """Archive one notification ("Archived")."""
        record = self._find(user_id, notification_id)
        if record is not None:
            record.in_app_status = InAppStatus.ARCHIVED

    def set_pinned(self, user_id: str, notification_id: str, *, pinned: bool) -> None:
        """Pin or unpin one notification ("Pinned")."""
        record = self._find(user_id, notification_id)
        if record is not None:
            record.pinned = pinned

    def unread_count(self, user_id: str) -> int:
        """The number of unread notifications for *user_id*."""
        return sum(
            1
            for record in self._records.get(user_id, [])
            if record.in_app_status == InAppStatus.UNREAD
        )

    def list_notifications(
        self,
        user_id: str,
        *,
        status: InAppStatus | None = None,
        category: str | None = None,
        page: int = 1,
        page_size: int = DEFAULT_IN_APP_PAGE_SIZE,
    ) -> list[InAppNotificationRecord]:
        """List *user_id*'s notifications, newest first ("Filtering", "Pagination")."""
        records = list(reversed(self._records.get(user_id, [])))
        if status is not None:
            records = [r for r in records if r.in_app_status == status]
        if category is not None:
            records = [r for r in records if r.category == category]
        start = (page - 1) * page_size
        return records[start : start + page_size]

    def search(self, user_id: str, query: str) -> list[InAppNotificationRecord]:
        """Search *user_id*'s notifications by substring in title/subject/body ("Search")."""
        query_lower = query.lower()
        return [
            record
            for record in reversed(self._records.get(user_id, []))
            if query_lower in (record.message.body or "").lower()
            or query_lower in (record.message.title or "").lower()
            or query_lower in (record.message.subject or "").lower()
        ]


class InAppChannel:
    """Delivers notifications into an :class:`InAppNotificationStore`."""

    channel_type = NotificationChannel.IN_APP

    def __init__(self, store: InAppNotificationStore):
        self._store = store

    async def send(self, message: NotificationMessage) -> DeliveryResult:
        self._store.add(message)
        return build_delivery_result(status=DeliveryStatus.DELIVERED, channel=self.channel_type)


__all__ = ["InAppChannel", "InAppNotificationRecord", "InAppNotificationStore", "InAppStatus"]
