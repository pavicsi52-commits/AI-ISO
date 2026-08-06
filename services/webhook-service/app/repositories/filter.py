"""The webhook filter repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.filter import WebhookFilter


class WebhookFilterRepository(BaseRepository[WebhookFilter]):
    """Event-filtering rule sets attached to a subscription."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WebhookFilter, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, filter_id: UUID) -> WebhookFilter:
        """One filter by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(WebhookFilter.organization_id == organization_id)
            .where(WebhookFilter.id == filter_id)
        )
        result = await self._session.execute(stmt)
        found: WebhookFilter | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No webhook filter with id {filter_id} in this organization.")
        return found

    async def list_for_subscription(self, subscription_id: UUID) -> list[WebhookFilter]:
        """Every enabled filter attached to one subscription."""
        stmt = (
            self._base_select()
            .where(WebhookFilter.subscription_id == subscription_id)
            .where(WebhookFilter.enabled.is_(True))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WebhookFilterRepository"]
