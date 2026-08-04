"""The notification subscription repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SubscriptionKind
from app.models.subscription import NotificationSubscription


class NotificationSubscriptionRepository(BaseRepository[NotificationSubscription]):
    """One user's own opt-ins."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, NotificationSubscription, tenant_scope=tenant_scope)

    async def find(
        self, organization_id: UUID, user_id: str, subscription_kind: SubscriptionKind, target: str
    ) -> NotificationSubscription | None:
        """The subscription row matching this exact natural key, if any."""
        stmt = (
            self._base_select()
            .where(NotificationSubscription.organization_id == organization_id)
            .where(NotificationSubscription.user_id == user_id)
            .where(NotificationSubscription.subscription_kind == str(subscription_kind))
            .where(NotificationSubscription.target == target)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_user(
        self, organization_id: UUID, user_id: str
    ) -> list[NotificationSubscription]:
        """Every subscription *user_id* currently holds in this organization."""
        stmt = (
            self._base_select()
            .where(NotificationSubscription.organization_id == organization_id)
            .where(NotificationSubscription.user_id == user_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_subscribers(
        self, organization_id: UUID, subscription_kind: SubscriptionKind, target: str
    ) -> list[str]:
        """Every user id subscribed to *target* ("Broadcast Groups": broadcast recipients)."""
        stmt = (
            self._base_select()
            .where(NotificationSubscription.organization_id == organization_id)
            .where(NotificationSubscription.subscription_kind == str(subscription_kind))
            .where(NotificationSubscription.target == target)
        )
        result = await self._session.execute(stmt)
        return sorted({row.user_id for row in result.scalars().all()})


__all__ = ["NotificationSubscriptionRepository"]
