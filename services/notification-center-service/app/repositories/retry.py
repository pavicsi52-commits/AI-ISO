"""The notification retry queue and dead letter repositories."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.retry import NotificationDeadLetter, NotificationRetryQueueEntry


class NotificationRetryQueueRepository(BaseRepository[NotificationRetryQueueEntry]):
    """One delivery's own pending retry.

    ``list_due`` is deliberately unscoped by organization -- the retry
    sweep is a single leader-elected worker walking every organization's
    due retries in one tick, the same pattern
    ``app.workers.retry_sweep`` (Prompt 054) already established.
    """

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, NotificationRetryQueueEntry, tenant_scope=tenant_scope)

    async def require_in_org(
        self, organization_id: UUID, entry_id: UUID
    ) -> NotificationRetryQueueEntry:
        """One retry-queue entry by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(NotificationRetryQueueEntry.organization_id == organization_id)
            .where(NotificationRetryQueueEntry.id == entry_id)
        )
        result = await self._session.execute(stmt)
        found: NotificationRetryQueueEntry | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No retry-queue entry with id {entry_id} in this organization.")
        return found

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        resolved: bool | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[NotificationRetryQueueEntry]:
        """Retry-queue entries in this organization, soonest-due first."""
        stmt = self._base_select().where(
            NotificationRetryQueueEntry.organization_id == organization_id
        )
        if resolved is not None:
            stmt = stmt.where(NotificationRetryQueueEntry.resolved.is_(resolved))
        stmt = stmt.order_by(NotificationRetryQueueEntry.next_retry_at).offset(offset).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_due(
        self, *, now: datetime, limit: int = 500
    ) -> list[NotificationRetryQueueEntry]:
        """Every unresolved retry entry due at or before *now*, across every organization."""
        stmt = (
            self._base_select()
            .where(NotificationRetryQueueEntry.resolved.is_(False))
            .where(NotificationRetryQueueEntry.next_retry_at <= now)
            .order_by(NotificationRetryQueueEntry.next_retry_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class NotificationDeadLetterRepository(BaseRepository[NotificationDeadLetter]):
    """One delivery that exhausted its retry policy."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, NotificationDeadLetter, tenant_scope=tenant_scope)

    async def require_in_org(
        self, organization_id: UUID, dead_letter_id: UUID
    ) -> NotificationDeadLetter:
        """One dead letter by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(NotificationDeadLetter.organization_id == organization_id)
            .where(NotificationDeadLetter.id == dead_letter_id)
        )
        result = await self._session.execute(stmt)
        found: NotificationDeadLetter | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No dead letter with id {dead_letter_id} in this organization.")
        return found

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        resolved: bool | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[NotificationDeadLetter]:
        """Dead letters in this organization, newest first."""
        stmt = self._base_select().where(NotificationDeadLetter.organization_id == organization_id)
        if resolved is not None:
            stmt = stmt.where(NotificationDeadLetter.resolved.is_(resolved))
        stmt = (
            stmt.order_by(NotificationDeadLetter.dead_lettered_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["NotificationDeadLetterRepository", "NotificationRetryQueueRepository"]
