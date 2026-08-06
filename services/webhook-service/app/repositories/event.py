"""The webhook event repository."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import WebhookEvent


class WebhookEventRepository(BaseRepository[WebhookEvent]):
    """Events received or raised, before fan-out to subscriptions."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WebhookEvent, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, event_id: UUID) -> WebhookEvent:
        """One event by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(WebhookEvent.organization_id == organization_id)
            .where(WebhookEvent.id == event_id)
        )
        result = await self._session.execute(stmt)
        found: WebhookEvent | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No webhook event with id {event_id} in this organization.")
        return found

    async def get_by_idempotency_key(
        self, organization_id: UUID, idempotency_key: str
    ) -> WebhookEvent | None:
        """The event previously recorded under *idempotency_key*, if any."""
        stmt = (
            self._base_select()
            .where(WebhookEvent.organization_id == organization_id)
            .where(WebhookEvent.idempotency_key == idempotency_key)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[WebhookEvent]:
        """Events in this organization, optionally bounded to a date range."""
        stmt = self._base_select().where(WebhookEvent.organization_id == organization_id)
        if since is not None:
            stmt = stmt.where(WebhookEvent.created_at >= since)
        if until is not None:
            stmt = stmt.where(WebhookEvent.created_at <= until)
        stmt = stmt.order_by(WebhookEvent.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WebhookEventRepository"]
