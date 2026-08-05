"""Broadcast fan-out.

One :class:`~app.models.announcement.NotificationBroadcast` row records
one fan-out *operation*; the actual recipients each get their own
:class:`~app.models.notification.Notification` row (created via
:class:`~app.services.notification.NotificationService`) sharing the
broadcast's own id as their ``correlation_id`` --
:meth:`~app.repositories.notification.NotificationRepository
.list_by_correlation` is how a caller finds every notification one
broadcast produced.

Recipients resolve from an explicit user-id list, a subscription topic
("Broadcast Groups"), or both, unioned. Resolving role/team/region/
environment audience targeting down to concrete user ids is
`services/rbac-service`/`services/organization-service`'s own directory
data -- out of this service's own scope to re-implement, per this
prompt's "use every previously implemented platform framework" and "Do
NOT redesign the platform" instructions; a caller wanting audience-based
targeting resolves it to a user-id list before calling this service.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.events.notification_events import SOURCE_SERVICE
from app.models.announcement import NotificationBroadcast
from app.models.enums import (
    BroadcastStatus,
    NotificationCategory,
    NotificationChannelKind,
    NotificationPriority,
    NotificationStatus,
    SubscriptionKind,
    notification_status_of,
)
from app.repositories.announcement import NotificationBroadcastRepository
from app.services.delivery import DeliveryService
from app.services.notification import NotificationService
from app.services.subscription import SubscriptionService

_SUCCESS_STATUSES = frozenset({NotificationStatus.SENT, NotificationStatus.DELIVERED})


class BroadcastService:
    """One fan-out send operation, and its resulting per-recipient notifications."""

    def __init__(
        self,
        broadcasts: NotificationBroadcastRepository,
        notifications: NotificationService,
        delivery: DeliveryService,
        subscriptions: SubscriptionService,
    ) -> None:
        self._broadcasts = broadcasts
        self._notifications = notifications
        self._delivery = delivery
        self._subscriptions = subscriptions

    async def broadcast(
        self,
        organization_id: UUID,
        *,
        body: str,
        category: NotificationCategory = NotificationCategory.SYSTEM_ANNOUNCEMENT,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        subject: str | None = None,
        channel: NotificationChannelKind | None = None,
        topic: str | None = None,
        recipient_user_ids: list[str] | None = None,
        announcement_id: UUID | None = None,
        initiated_by: str | None = None,
    ) -> NotificationBroadcast:
        """Fan *body* out to every resolved recipient, each over their own resolved channel(s)."""
        recipients = set(recipient_user_ids or [])
        if topic is not None:
            recipients.update(
                await self._subscriptions.subscribers_of(
                    organization_id, SubscriptionKind.TOPIC, topic
                )
            )
        recipient_list = sorted(recipients)

        broadcast = await self._broadcasts.create(
            NotificationBroadcast(
                organization_id=organization_id,
                announcement_id=announcement_id,
                topic=topic,
                category=category,
                priority=priority,
                channel=channel,
                subject=subject,
                body=body,
                status=BroadcastStatus.IN_PROGRESS,
                total_recipients=len(recipient_list),
                initiated_by=initiated_by,
                initiated_at=datetime.now(UTC),
            )
        )

        sent_count = 0
        failed_count = 0
        for user_id in recipient_list:
            notification = await self._notifications.create(
                organization_id,
                user_id=user_id,
                category=category,
                priority=priority,
                subject=subject,
                body=body,
                source_service=SOURCE_SERVICE,
                source_event_type="broadcast",
                correlation_id=str(broadcast.id),
            )
            deliveries = await self._delivery.dispatch(
                organization_id, notification, requested_channel=channel
            )
            if any(notification_status_of(d.status) in _SUCCESS_STATUSES for d in deliveries):
                sent_count += 1
            else:
                failed_count += 1

        broadcast.sent_count = sent_count
        broadcast.failed_count = failed_count
        broadcast.status = BroadcastStatus.COMPLETED
        broadcast.completed_at = datetime.now(UTC)
        return await self._broadcasts.update(broadcast)

    async def get(self, organization_id: UUID, broadcast_id: UUID) -> NotificationBroadcast:
        """One broadcast.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._broadcasts.require_in_org(organization_id, broadcast_id)

    async def list_broadcasts(
        self, organization_id: UUID, *, status: BroadcastStatus | None = None
    ) -> list[NotificationBroadcast]:
        """Broadcasts in this organization, newest first."""
        return await self._broadcasts.list_for_org(organization_id, status=status)


__all__ = ["BroadcastService"]
