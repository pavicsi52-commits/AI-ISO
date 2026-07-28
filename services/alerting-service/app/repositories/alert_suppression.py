"""Repository for :class:`app.models.alert_suppression.AlertSuppression`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_suppression import AlertSuppression


class AlertSuppressionRepository(BaseRepository[AlertSuppression]):
    """CRUD plus lookup for :class:`AlertSuppression`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AlertSuppression, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[AlertSuppression]:
        """Every suppression rule belonging to *organization_id*."""
        stmt = self._base_select().where(AlertSuppression.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_active_at(
        self, organization_id: UUID, moment: datetime
    ) -> list[AlertSuppression]:
        """Every enabled suppression in force at *moment*.

        An open-ended suppression (``ends_at IS NULL``) stays in force
        indefinitely until explicitly disabled.
        """
        stmt = self._base_select().where(
            AlertSuppression.organization_id == organization_id,
            AlertSuppression.enabled.is_(True),
            AlertSuppression.starts_at <= moment,
            or_(AlertSuppression.ends_at.is_(None), AlertSuppression.ends_at >= moment),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AlertSuppressionRepository"]
