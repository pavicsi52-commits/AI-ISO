"""The notification delivery and delivery attempt repositories."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.delivery import NotificationDelivery, NotificationDeliveryAttempt


class NotificationDeliveryRepository(BaseRepository[NotificationDelivery]):
    """One channel's own attempt to reach one recipient."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, NotificationDelivery, tenant_scope=tenant_scope)

    async def require_in_org(
        self, organization_id: UUID, delivery_id: UUID
    ) -> NotificationDelivery:
        """One delivery by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(NotificationDelivery.organization_id == organization_id)
            .where(NotificationDelivery.id == delivery_id)
        )
        result = await self._session.execute(stmt)
        found: NotificationDelivery | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No delivery with id {delivery_id} in this organization.")
        return found

    async def list_for_notification(
        self, organization_id: UUID, notification_id: UUID
    ) -> list[NotificationDelivery]:
        """Every channel this notification was (or is being) delivered over."""
        stmt = (
            self._base_select()
            .where(NotificationDelivery.organization_id == organization_id)
            .where(NotificationDelivery.notification_id == notification_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status(self, organization_id: UUID) -> dict[str, int]:
        """How many deliveries sit in each status."""
        stmt = (
            select(NotificationDelivery.status, func.count())
            .where(NotificationDelivery.organization_id == organization_id)
            .where(NotificationDelivery.deleted_at.is_(None))
            .group_by(NotificationDelivery.status)
        )
        rows = (await self._session.execute(stmt)).all()
        return {str(status): int(count) for status, count in rows}

    async def list_recent(
        self, organization_id: UUID, *, limit: int = 200
    ) -> list[NotificationDelivery]:
        """The most recently queued deliveries, newest first."""
        stmt = (
            self._base_select()
            .where(NotificationDelivery.organization_id == organization_id)
            .order_by(NotificationDelivery.queued_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_created_in_window(
        self, organization_id: UUID, *, start: datetime, end: datetime, limit: int = 10_000
    ) -> list[NotificationDelivery]:
        """Deliveries queued within a window, for statistics rollups."""
        stmt = (
            self._base_select()
            .where(NotificationDelivery.organization_id == organization_id)
            .where(NotificationDelivery.queued_at >= start)
            .where(NotificationDelivery.queued_at < end)
            .order_by(NotificationDelivery.queued_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class NotificationDeliveryAttemptRepository(BaseRepository[NotificationDeliveryAttempt]):
    """One individual send attempt."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, NotificationDeliveryAttempt, tenant_scope=tenant_scope)

    async def list_for_delivery(
        self, organization_id: UUID, delivery_id: UUID
    ) -> list[NotificationDeliveryAttempt]:
        """Every attempt made for one delivery, in attempt order."""
        stmt = (
            self._base_select()
            .where(NotificationDeliveryAttempt.organization_id == organization_id)
            .where(NotificationDeliveryAttempt.delivery_id == delivery_id)
            .order_by(NotificationDeliveryAttempt.attempt_number)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["NotificationDeliveryAttemptRepository", "NotificationDeliveryRepository"]
