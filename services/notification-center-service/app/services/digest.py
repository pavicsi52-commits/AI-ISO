"""Digest building and sending.

Bundles a user's own unread notifications from the last digest window
into one summarizing notification (category ``DIGEST``), grouped and
deduplicated via :mod:`app.digest.engine` (a thin adapter onto
`shared_core.notifications.digest`), then dispatched exactly like any
other notification through :class:`~app.services.delivery
.DeliveryService`.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Final
from uuid import UUID

from app.digest import engine as digest_engine
from app.events.notification_events import SOURCE_SERVICE
from app.models.enums import (
    DigestFrequency,
    NotificationCategory,
    NotificationPriority,
    digest_frequency_of,
    notification_category_of,
    notification_priority_of,
)
from app.models.notification import Notification
from app.repositories.notification import NotificationRepository
from app.services.delivery import DeliveryService
from app.services.notification import NotificationService
from app.services.preference import PreferenceService

_WINDOW_HOURS: Final[dict[DigestFrequency, int]] = {
    DigestFrequency.HOURLY: 1,
    DigestFrequency.DAILY: 24,
    DigestFrequency.WEEKLY: 24 * 7,
    DigestFrequency.MONTHLY: 24 * 30,
}


class DigestService:
    """Builds and sends one user's own bundled digest."""

    def __init__(
        self,
        notification_repository: NotificationRepository,
        preferences: PreferenceService,
        notifications: NotificationService,
        delivery: DeliveryService,
        *,
        max_items: int,
    ) -> None:
        self._notification_repository = notification_repository
        self._preferences = preferences
        self._notifications = notifications
        self._delivery = delivery
        self._max_items = max_items

    async def build_and_send(
        self, organization_id: UUID, user_id: str, *, now: datetime
    ) -> Notification | None:
        """Build and send *user_id*'s digest, or return ``None`` if there is nothing to bundle.

        ``None`` when the user's own preference is ``DigestFrequency.NONE``
        (no digest wanted) or there is nothing unread in the window.
        """
        preference_row = await self._preferences.get(organization_id, user_id)
        frequency = digest_frequency_of(preference_row.digest_frequency)
        if frequency == DigestFrequency.NONE:
            return None

        window_start = now - timedelta(hours=_WINDOW_HOURS[frequency])
        candidates = [
            notification
            for notification in await self._notification_repository.list_created_in_window(
                organization_id, start=window_start, end=now
            )
            if notification.read_at is None
            and notification_category_of(notification.category) != NotificationCategory.DIGEST
        ]
        if not candidates:
            return None

        shared_messages = [
            digest_engine.to_shared_message(
                notification_id=str(notification.id),
                category=notification_category_of(notification.category),
                priority=notification_priority_of(notification.priority),
                subject=notification.subject,
                body=notification.body,
                user_id=user_id,
            )
            for notification in candidates
        ]
        digest = digest_engine.build_user_digest(
            user_id, shared_messages, max_items=self._max_items
        )
        body = digest_engine.render_digest_body(digest)

        digest_notification = await self._notifications.create(
            organization_id,
            user_id=user_id,
            category=NotificationCategory.DIGEST,
            priority=NotificationPriority.LOW,
            subject=f"Your {frequency.value} digest",
            body=body,
            source_service=SOURCE_SERVICE,
            source_event_type="digest",
        )
        await self._delivery.dispatch(organization_id, digest_notification)
        return digest_notification


__all__ = ["DigestService"]
