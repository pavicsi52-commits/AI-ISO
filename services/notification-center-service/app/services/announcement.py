"""Announcement creation, publication, and expiry.

Publishing an announcement never sends anything by itself -- it flips
:attr:`~app.models.announcement.NotificationAnnouncement.status` to
``PUBLISHED`` and publishes ``AnnouncementPublished``.
:class:`~app.services.broadcast.BroadcastService` is what actually fans
an announcement out into per-recipient notifications, kept as a
separate step so an announcement can be published to the in-app
"Announcements" feed without necessarily also pushing a notification to
every targeted recipient's other channels (a caller who wants both calls
:meth:`AnnouncementService.publish` and then
:meth:`~app.services.broadcast.BroadcastService.broadcast_announcement`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.events.notification_events import SOURCE_SERVICE, AnnouncementPublishedEvent
from app.models.announcement import NotificationAnnouncement
from app.models.enums import AnnouncementScope, AnnouncementStatus
from app.repositories.announcement import NotificationAnnouncementRepository
from app.types import EventPublisher

_EDITABLE_FIELDS = frozenset({"title", "body", "is_pinned", "starts_at", "expires_at", "audience"})


class AnnouncementService:
    """Announcements: creation, publication, and expiry."""

    def __init__(
        self,
        announcements: NotificationAnnouncementRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._announcements = announcements
        self._publish = publish_event

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def create(
        self,
        organization_id: UUID,
        *,
        scope: AnnouncementScope,
        title: str,
        body: str,
        is_pinned: bool = False,
        starts_at: datetime | None = None,
        expires_at: datetime | None = None,
        audience: dict[str, Any] | None = None,
        actor_id: str | None = None,
    ) -> NotificationAnnouncement:
        """Draft a new announcement -- not yet visible until :meth:`publish`.

        Raises:
            ValidationError: If ``expires_at`` is not after ``starts_at``.
        """
        if starts_at is not None and expires_at is not None and expires_at <= starts_at:
            raise ValidationError("An announcement's expires_at must be after its starts_at.")
        return await self._announcements.create(
            NotificationAnnouncement(
                organization_id=organization_id,
                scope=scope,
                status=AnnouncementStatus.DRAFT,
                title=title,
                body=body,
                is_pinned=is_pinned,
                starts_at=starts_at,
                expires_at=expires_at,
                audience=dict(audience or {}),
                created_by=UUID(actor_id) if actor_id else None,
            )
        )

    async def get(self, organization_id: UUID, announcement_id: UUID) -> NotificationAnnouncement:
        """One announcement.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._announcements.require_in_org(organization_id, announcement_id)

    async def list_announcements(
        self, organization_id: UUID, *, status: AnnouncementStatus | None = None
    ) -> list[NotificationAnnouncement]:
        """Announcements in this organization, pinned first."""
        return await self._announcements.list_for_org(organization_id, status=status)

    async def update(
        self, organization_id: UUID, announcement_id: UUID, *, actor_id: str | None = None, **fields: Any
    ) -> NotificationAnnouncement:
        """Edit a draft announcement's editable fields."""
        stored = await self._announcements.require_in_org(organization_id, announcement_id)
        for field, value in fields.items():
            if field in _EDITABLE_FIELDS and value is not None:
                setattr(stored, field, value)
        stored.updated_by = UUID(actor_id) if actor_id else None
        return await self._announcements.update(stored)

    async def publish(
        self, organization_id: UUID, announcement_id: UUID, *, actor_id: str | None = None
    ) -> NotificationAnnouncement:
        """Publish an announcement, making it visible to its audience.

        Raises:
            ValidationError: If it is already published.
        """
        stored = await self._announcements.require_in_org(organization_id, announcement_id)
        if AnnouncementStatus(stored.status) == AnnouncementStatus.PUBLISHED:
            raise ValidationError(f"Announcement {announcement_id} is already published.")
        stored.status = AnnouncementStatus.PUBLISHED
        stored.published_at = datetime.now(UTC)
        stored.updated_by = UUID(actor_id) if actor_id else None
        updated = await self._announcements.update(stored)
        await self._publish_event(
            AnnouncementPublishedEvent(
                source_service=SOURCE_SERVICE,
                organization_id=organization_id,
                payload={
                    "announcement_id": str(updated.id),
                    "scope": str(updated.scope),
                    "title": updated.title,
                },
            )
        )
        return updated

    async def archive(
        self, organization_id: UUID, announcement_id: UUID, *, actor_id: str | None = None
    ) -> NotificationAnnouncement:
        """Archive an announcement, removing it from the active feed."""
        stored = await self._announcements.require_in_org(organization_id, announcement_id)
        stored.status = AnnouncementStatus.ARCHIVED
        stored.updated_by = UUID(actor_id) if actor_id else None
        return await self._announcements.update(stored)

    async def expire_due(self, *, now: datetime, limit: int = 500) -> int:
        """Expire every published announcement whose ``expires_at`` has passed.

        The announcement-expiry sweep's own entry point.
        """
        due = await self._announcements.list_due_for_expiry(now=now, limit=limit)
        for announcement in due:
            announcement.status = AnnouncementStatus.EXPIRED
            await self._announcements.update(announcement)
        return len(due)


__all__ = ["AnnouncementService"]
