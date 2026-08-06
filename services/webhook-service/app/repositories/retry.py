"""The webhook retry-queue and dead-letter repositories."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.retry import WebhookDeadLetter, WebhookRetryQueueEntry


class WebhookRetryQueueRepository(BaseRepository[WebhookRetryQueueEntry]):
    """Pending retries, one row per delivery currently awaiting its next attempt."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WebhookRetryQueueEntry, tenant_scope=tenant_scope)

    async def get_for_delivery(self, delivery_id: UUID) -> WebhookRetryQueueEntry | None:
        """The pending retry entry for one delivery, if any."""
        stmt = self._base_select().where(WebhookRetryQueueEntry.delivery_id == delivery_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_due(self, *, now: datetime, limit: int = 500) -> list[WebhookRetryQueueEntry]:
        """Every retry entry whose own ``next_attempt_at`` has arrived, across every organization.

        Unscoped by organization -- the retry sweep is a single
        leader-elected worker walking every organization's due retries
        in one tick.
        """
        stmt = (
            self._base_select()
            .where(WebhookRetryQueueEntry.next_attempt_at <= now)
            .order_by(WebhookRetryQueueEntry.next_attempt_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class WebhookDeadLetterRepository(BaseRepository[WebhookDeadLetter]):
    """Deliveries that exhausted their own retry policy."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WebhookDeadLetter, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, dead_letter_id: UUID) -> WebhookDeadLetter:
        """One dead-letter row by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(WebhookDeadLetter.organization_id == organization_id)
            .where(WebhookDeadLetter.id == dead_letter_id)
        )
        result = await self._session.execute(stmt)
        found: WebhookDeadLetter | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No dead letter with id {dead_letter_id} in this organization.")
        return found

    async def list_for_org(
        self, organization_id: UUID, *, replayed: bool | None = None, limit: int = 200
    ) -> list[WebhookDeadLetter]:
        """Dead-lettered deliveries in this organization, newest first."""
        stmt = self._base_select().where(WebhookDeadLetter.organization_id == organization_id)
        if replayed is not None:
            stmt = stmt.where(WebhookDeadLetter.replayed.is_(replayed))
        stmt = stmt.order_by(WebhookDeadLetter.dead_lettered_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WebhookDeadLetterRepository", "WebhookRetryQueueRepository"]
