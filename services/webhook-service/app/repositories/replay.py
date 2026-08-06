"""The webhook replay job repository."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReplayStatus
from app.models.replay import WebhookReplayJob


class WebhookReplayJobRepository(BaseRepository[WebhookReplayJob]):
    """Requests to redeliver a past slice of events."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WebhookReplayJob, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, job_id: UUID) -> WebhookReplayJob:
        """One replay job by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(WebhookReplayJob.organization_id == organization_id)
            .where(WebhookReplayJob.id == job_id)
        )
        result = await self._session.execute(stmt)
        found: WebhookReplayJob | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No replay job with id {job_id} in this organization.")
        return found

    async def list_for_org(self, organization_id: UUID, *, limit: int = 200) -> list[WebhookReplayJob]:
        """Replay jobs in this organization, newest first."""
        stmt = (
            self._base_select()
            .where(WebhookReplayJob.organization_id == organization_id)
            .order_by(WebhookReplayJob.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_pending(self, *, limit: int = 50) -> list[WebhookReplayJob]:
        """Every ``PENDING`` job across every organization -- for the replay-processor sweep."""
        stmt = (
            self._base_select()
            .where(WebhookReplayJob.status == str(ReplayStatus.PENDING))
            .order_by(WebhookReplayJob.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WebhookReplayJobRepository"]
