"""Repository for :class:`app.models.alert_history.AlertHistory`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_history import AlertHistory


class AlertHistoryRepository(BaseRepository[AlertHistory]):
    """CRUD plus lookup for :class:`AlertHistory`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AlertHistory, tenant_scope=tenant_scope)

    async def list_for_alert(self, alert_id: UUID) -> list[AlertHistory]:
        """Every status transition for *alert_id*, oldest first."""
        stmt = (
            self._base_select()
            .where(AlertHistory.alert_id == alert_id)
            .order_by(AlertHistory.changed_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(self, organization_id: UUID) -> list[AlertHistory]:
        """Every status transition for *organization_id*, oldest first."""
        stmt = (
            self._base_select()
            .where(AlertHistory.organization_id == organization_id)
            .order_by(AlertHistory.changed_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AlertHistoryRepository"]
