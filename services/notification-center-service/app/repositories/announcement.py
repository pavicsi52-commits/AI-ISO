"""The notification announcement and broadcast repositories."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.announcement import NotificationAnnouncement, NotificationBroadcast
from app.models.enums import AnnouncementStatus, BroadcastStatus


class NotificationAnnouncementRepository(BaseRepository[NotificationAnnouncement]):
    """One persistent, targetable announcement."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, NotificationAnnouncement, tenant_scope=tenant_scope)

    async def require_in_org(
        self, organization_id: UUID, announcement_id: UUID
    ) -> NotificationAnnouncement:
        """One announcement by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(NotificationAnnouncement.organization_id == organization_id)
            .where(NotificationAnnouncement.id == announcement_id)
        )
        result = await self._session.execute(stmt)
        found: NotificationAnnouncement | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No announcement with id {announcement_id} in this organization.")
        return found

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        status: AnnouncementStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[NotificationAnnouncement]:
        """Announcements in this organization, pinned first, then newest."""
        stmt = self._base_select().where(
            NotificationAnnouncement.organization_id == organization_id
        )
        if status is not None:
            stmt = stmt.where(NotificationAnnouncement.status == str(status))
        stmt = (
            stmt.order_by(
                NotificationAnnouncement.is_pinned.desc(),
                NotificationAnnouncement.created_at.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_due_for_expiry(
        self, *, now: datetime, limit: int = 500
    ) -> list[NotificationAnnouncement]:
        """Every still-``PUBLISHED`` announcement whose ``expires_at`` has passed.

        Unscoped by organization -- the announcement-expiry sweep is a
        single leader-elected worker walking every organization's due
        expirations in one tick.
        """
        stmt = (
            self._base_select()
            .where(NotificationAnnouncement.status == str(AnnouncementStatus.PUBLISHED))
            .where(NotificationAnnouncement.expires_at.is_not(None))
            .where(NotificationAnnouncement.expires_at <= now)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class NotificationBroadcastRepository(BaseRepository[NotificationBroadcast]):
    """One fan-out send operation."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, NotificationBroadcast, tenant_scope=tenant_scope)

    async def require_in_org(
        self, organization_id: UUID, broadcast_id: UUID
    ) -> NotificationBroadcast:
        """One broadcast by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(NotificationBroadcast.organization_id == organization_id)
            .where(NotificationBroadcast.id == broadcast_id)
        )
        result = await self._session.execute(stmt)
        found: NotificationBroadcast | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No broadcast with id {broadcast_id} in this organization.")
        return found

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        status: BroadcastStatus | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[NotificationBroadcast]:
        """Broadcasts in this organization, newest first."""
        stmt = self._base_select().where(NotificationBroadcast.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(NotificationBroadcast.status == str(status))
        stmt = stmt.order_by(NotificationBroadcast.initiated_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["NotificationAnnouncementRepository", "NotificationBroadcastRepository"]
