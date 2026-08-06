"""The webhook subscription repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subscription import WebhookSubscription


class WebhookSubscriptionRepository(BaseRepository[WebhookSubscription]):
    """Endpoint subscriptions to event sources/types."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WebhookSubscription, tenant_scope=tenant_scope)

    async def require_in_org(
        self, organization_id: UUID, subscription_id: UUID
    ) -> WebhookSubscription:
        """One subscription by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(WebhookSubscription.organization_id == organization_id)
            .where(WebhookSubscription.id == subscription_id)
        )
        result = await self._session.execute(stmt)
        found: WebhookSubscription | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No subscription with id {subscription_id} in this organization.")
        return found

    async def list_for_org(self, organization_id: UUID) -> list[WebhookSubscription]:
        """Subscriptions in this organization."""
        stmt = self._base_select().where(WebhookSubscription.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_enabled_for_org(self, organization_id: UUID) -> list[WebhookSubscription]:
        """Every enabled subscription in this organization -- the fan-out candidate set."""
        stmt = (
            self._base_select()
            .where(WebhookSubscription.organization_id == organization_id)
            .where(WebhookSubscription.enabled.is_(True))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_endpoint(
        self, organization_id: UUID, endpoint_id: UUID
    ) -> list[WebhookSubscription]:
        """Every subscription belonging to one endpoint."""
        stmt = (
            self._base_select()
            .where(WebhookSubscription.organization_id == organization_id)
            .where(WebhookSubscription.endpoint_id == endpoint_id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WebhookSubscriptionRepository"]
