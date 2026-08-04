"""Notification creation, reads, acknowledgement, and cancellation.

Creating a notification never dispatches it -- that is
:class:`~app.services.delivery.DeliveryService`'s job, kept as a
separate step so a caller (an HTTP request or
:class:`~app.services.broadcast.BroadcastService`'s own fan-out) can
create a batch of notifications and dispatch them independently, and so
a notification's own row exists to attach delivery/retry/dead-letter
state to before any channel I/O has happened.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.events.notification_events import SOURCE_SERVICE, NotificationCreatedEvent
from app.models.enums import (
    OPEN_NOTIFICATION_STATUSES,
    NotificationCategory,
    NotificationPriority,
    NotificationStatus,
)
from app.models.notification import Notification
from app.repositories.notification import NotificationRepository
from app.types import EventPublisher


class NotificationService:
    """Notifications: creation, reads, acknowledgement, and cancellation."""

    def __init__(
        self, notifications: NotificationRepository, *, publish_event: EventPublisher | None = None
    ) -> None:
        self._notifications = notifications
        self._publish = publish_event

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def create(
        self,
        organization_id: UUID,
        *,
        user_id: str,
        category: NotificationCategory,
        source_service: str,
        body: str,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        subject: str | None = None,
        template_id: UUID | None = None,
        template_variables: dict[str, Any] | None = None,
        source_event_type: str | None = None,
        correlation_id: str | None = None,
        expires_at: datetime | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        actor_id: str | None = None,
    ) -> Notification:
        """Create a new notification, ``CREATED`` and not yet dispatched."""
        created = await self._notifications.create(
            Notification(
                organization_id=organization_id,
                user_id=user_id,
                category=category,
                priority=priority,
                status=NotificationStatus.CREATED,
                subject=subject,
                body=body,
                template_id=template_id,
                template_variables=dict(template_variables or {}),
                source_service=source_service,
                source_event_type=source_event_type,
                correlation_id=correlation_id,
                expires_at=expires_at,
                tags=list(tags or []),
                notification_metadata=dict(metadata or {}),
                created_by=UUID(actor_id) if actor_id else None,
            )
        )
        await self._publish_event(
            NotificationCreatedEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={
                    "notification_id": str(created.id),
                    "user_id": created.user_id,
                    "category": str(created.category),
                    "source_service": created.source_service,
                },
            )
        )
        return created

    async def get(self, organization_id: UUID, notification_id: UUID) -> Notification:
        """One notification.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._notifications.require_in_org(organization_id, notification_id)

    async def list_notifications(
        self,
        organization_id: UUID,
        *,
        user_id: str | None = None,
        status: NotificationStatus | None = None,
        category: NotificationCategory | None = None,
        source_service: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Notification]:
        """Notifications matching a caller's filters."""
        return await self._notifications.list_filtered(
            organization_id,
            user_id=user_id,
            status=status,
            category=category,
            source_service=source_service,
            limit=limit,
            offset=offset,
        )

    async def mark_read(self, organization_id: UUID, notification_id: UUID) -> Notification:
        """Mark a notification as read.

        A no-op if already read -- reading twice is not an error.
        """
        stored = await self._notifications.require_in_org(organization_id, notification_id)
        if stored.read_at is None:
            stored.read_at = datetime.now(UTC)
            if stored.status not in (NotificationStatus.ACKNOWLEDGED,):
                stored.status = NotificationStatus.READ
            await self._notifications.update(stored)
        return stored

    async def acknowledge(self, organization_id: UUID, notification_id: UUID) -> Notification:
        """Mark a notification as acknowledged (a stronger signal than "read")."""
        stored = await self._notifications.require_in_org(organization_id, notification_id)
        moment = datetime.now(UTC)
        if stored.read_at is None:
            stored.read_at = moment
        stored.acknowledged_at = moment
        stored.status = NotificationStatus.ACKNOWLEDGED
        await self._notifications.update(stored)
        return stored

    async def cancel(self, organization_id: UUID, notification_id: UUID) -> Notification:
        """Cancel a notification that has not reached a terminal state yet.

        Raises:
            ValidationError: If it is already in a terminal status.
        """
        stored = await self._notifications.require_in_org(organization_id, notification_id)
        if NotificationStatus(stored.status) not in OPEN_NOTIFICATION_STATUSES:
            raise ValidationError(
                f"Notification {notification_id} is already {stored.status} and cannot be cancelled."
            )
        stored.status = NotificationStatus.CANCELLED
        await self._notifications.update(stored)
        return stored

    async def delete(
        self, organization_id: UUID, notification_id: UUID, *, actor_id: str | None = None
    ) -> None:
        """Soft-delete a notification."""
        stored = await self._notifications.require_in_org(organization_id, notification_id)
        await self._notifications.delete(stored.id, deleted_by=UUID(actor_id) if actor_id else None)


__all__ = ["NotificationService"]
