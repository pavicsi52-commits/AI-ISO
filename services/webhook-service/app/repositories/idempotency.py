"""The webhook idempotency-key repository."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency import WebhookIdempotencyKey


class WebhookIdempotencyKeyRepository(BaseRepository[WebhookIdempotencyKey]):
    """Caller-supplied idempotency keys and their own settled results."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WebhookIdempotencyKey, tenant_scope=tenant_scope)

    async def get_by_key(
        self, organization_id: UUID, idempotency_key: str
    ) -> WebhookIdempotencyKey | None:
        """The row previously recorded for *idempotency_key*, if any."""
        stmt = (
            self._base_select()
            .where(WebhookIdempotencyKey.organization_id == organization_id)
            .where(WebhookIdempotencyKey.idempotency_key == idempotency_key)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_expired(self, *, now: datetime, limit: int = 500) -> list[WebhookIdempotencyKey]:
        """Every key whose own expiry has already passed, across every organization.

        Unscoped by organization -- the idempotency-expiry sweep is a
        single leader-elected worker walking every organization's due
        expirations in one tick.
        """
        stmt = self._base_select().where(WebhookIdempotencyKey.expires_at <= now).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WebhookIdempotencyKeyRepository"]
