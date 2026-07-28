"""Repository for :class:`app.models.alert_notification.AlertNotification`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_notification import AlertNotification
from app.models.enums import NotificationDeliveryStatus


class AlertNotificationRepository(BaseRepository[AlertNotification]):
    """CRUD plus lookup for :class:`AlertNotification`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AlertNotification, tenant_scope=tenant_scope)

    async def list_for_alert(self, alert_id: UUID) -> list[AlertNotification]:
        """Every delivery attempt recorded for *alert_id*."""
        stmt = self._base_select().where(AlertNotification.alert_id == alert_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_retryable(self, organization_id: UUID) -> list[AlertNotification]:
        """Every failed/retrying delivery attempt awaiting another try ("Retry")."""
        stmt = self._base_select().where(
            AlertNotification.organization_id == organization_id,
            AlertNotification.status.in_(
                (NotificationDeliveryStatus.FAILED, NotificationDeliveryStatus.RETRYING)
            ),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AlertNotificationRepository"]
