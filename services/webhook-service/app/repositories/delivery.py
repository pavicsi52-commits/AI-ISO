"""The webhook delivery and delivery-attempt repositories."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.delivery import WebhookDelivery, WebhookDeliveryAttempt
from app.models.enums import DeliveryStatus


class WebhookDeliveryRepository(BaseRepository[WebhookDelivery]):
    """One event's own delivery to one endpoint."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WebhookDelivery, tenant_scope=tenant_scope)

    async def require_in_org(self, organization_id: UUID, delivery_id: UUID) -> WebhookDelivery:
        """One delivery by id, scoped to its organization.

        Raises:
            NotFoundError: If it does not exist here.
        """
        stmt = (
            self._base_select()
            .where(WebhookDelivery.organization_id == organization_id)
            .where(WebhookDelivery.id == delivery_id)
        )
        result = await self._session.execute(stmt)
        found: WebhookDelivery | None = result.scalars().first()
        if found is None:
            raise NotFoundError(f"No delivery with id {delivery_id} in this organization.")
        return found

    async def list_for_org(
        self,
        organization_id: UUID,
        *,
        status: DeliveryStatus | None = None,
        endpoint_id: UUID | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[WebhookDelivery]:
        """Deliveries in this organization, newest first."""
        stmt = self._base_select().where(WebhookDelivery.organization_id == organization_id)
        if status is not None:
            stmt = stmt.where(WebhookDelivery.status == str(status))
        if endpoint_id is not None:
            stmt = stmt.where(WebhookDelivery.endpoint_id == endpoint_id)
        stmt = stmt.order_by(WebhookDelivery.created_at.desc()).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_idempotency_key(
        self, organization_id: UUID, endpoint_id: UUID, idempotency_key: str
    ) -> WebhookDelivery | None:
        """The delivery previously queued for this exact (endpoint, key) pair, if any."""
        stmt = (
            self._base_select()
            .where(WebhookDelivery.organization_id == organization_id)
            .where(WebhookDelivery.endpoint_id == endpoint_id)
            .where(WebhookDelivery.idempotency_key == idempotency_key)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


class WebhookDeliveryAttemptRepository(BaseRepository[WebhookDeliveryAttempt]):
    """Concrete HTTP attempts for one delivery."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, WebhookDeliveryAttempt, tenant_scope=tenant_scope)

    async def list_for_delivery(self, delivery_id: UUID) -> list[WebhookDeliveryAttempt]:
        """Every attempt for one delivery, in attempt order."""
        stmt = (
            self._base_select()
            .where(WebhookDeliveryAttempt.delivery_id == delivery_id)
            .order_by(WebhookDeliveryAttempt.attempt_number)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_created_in_window(
        self, organization_id: UUID, *, start: datetime, end: datetime, limit: int = 10_000
    ) -> list[WebhookDeliveryAttempt]:
        """Attempts recorded in ``[start, end)`` for one organization -- for statistics rollup."""
        stmt = (
            self._base_select()
            .where(WebhookDeliveryAttempt.organization_id == organization_id)
            .where(WebhookDeliveryAttempt.attempted_at >= start)
            .where(WebhookDeliveryAttempt.attempted_at < end)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["WebhookDeliveryAttemptRepository", "WebhookDeliveryRepository"]
