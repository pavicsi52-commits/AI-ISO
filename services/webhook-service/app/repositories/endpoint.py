"""The webhook endpoint repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.endpoint import WebhookEndpoint


class WebhookEndpointRepository(BaseRepository[WebhookEndpoint]):
    """Registered outgoing-delivery targets."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WebhookEndpoint, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, endpoint_id: UUID) -> WebhookEndpoint:
        """One endpoint by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(WebhookEndpoint.organization_id == organization_id)
            .where(WebhookEndpoint.id == endpoint_id)
        )
        result = await self._session.execute(stmt)
        found: WebhookEndpoint | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No webhook endpoint with id {endpoint_id} in this organization.")
        return found

    async def list_for_org(
        self, organization_id: UUID, *, enabled: bool | None = None
    ) -> list[WebhookEndpoint]:
        """Endpoints registered in this organization."""
        stmt = self._base_select().where(WebhookEndpoint.organization_id == organization_id)
        if enabled is not None:
            stmt = stmt.where(WebhookEndpoint.enabled.is_(enabled))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_enabled(self, *, limit: int = 500) -> list[WebhookEndpoint]:
        """Every enabled endpoint across every organization -- for the health-check sweep."""
        stmt = self._base_select().where(WebhookEndpoint.enabled.is_(True)).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WebhookEndpointRepository"]
