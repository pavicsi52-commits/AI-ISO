"""The notification repository.

Every read is scoped by ``organization_id``. ``require_in_org`` is named
apart from the base repository's unscoped ``require_by_id``, per this
repository's established convention: two same-named methods of different
arity on one class make an unscoped call look correct.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NotificationCategory, NotificationStatus
from app.models.notification import Notification


class NotificationRepository(BaseRepository[Notification]):
    """The notification catalogue."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, Notification, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, notification_id: UUID) -> Notification:
        """One notification by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(Notification.organization_id == organization_id)
            .where(Notification.id == notification_id)
        )
        result = await self._session.execute(stmt)
        found: Notification | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No notification with id {notification_id} in this organization.")
        return found

    async def list_filtered(
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
        """Notifications matching a caller's filters, newest first."""
        stmt = self._base_select().where(Notification.organization_id == organization_id)
        if user_id is not None:
            stmt = stmt.where(Notification.user_id == user_id)
        if status is not None:
            stmt = stmt.where(Notification.status == str(status))
        if category is not None:
            stmt = stmt.where(Notification.category == str(category))
        if source_service is not None:
            stmt = stmt.where(Notification.source_service == source_service)
        stmt = stmt.order_by(Notification.created_at.desc()).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_correlation(
        self, organization_id: UUID, correlation_id: str, *, limit: int = 10_000
    ) -> list[Notification]:
        """Every recipient's own row from the same broadcast or fan-out."""
        stmt = (
            self._base_select()
            .where(Notification.organization_id == organization_id)
            .where(Notification.correlation_id == correlation_id)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_unread(self, organization_id: UUID, user_id: str) -> int:
        """How many of *user_id*'s notifications have not been read yet."""
        stmt = (
            self._base_select()
            .where(Notification.organization_id == organization_id)
            .where(Notification.user_id == user_id)
            .where(Notification.read_at.is_(None))
        )
        result = await self._session.execute(stmt)
        return len(result.scalars().all())

    async def list_created_in_window(
        self, organization_id: UUID, *, start: datetime, end: datetime, limit: int = 10_000
    ) -> list[Notification]:
        """Notifications created within a window, for statistics rollups."""
        stmt = (
            self._base_select()
            .where(Notification.organization_id == organization_id)
            .where(Notification.created_at >= start)
            .where(Notification.created_at < end)
            .order_by(Notification.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["NotificationRepository"]
