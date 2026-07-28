"""Repository for :class:`app.models.alert_correlation.AlertCorrelation`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_correlation import AlertCorrelation


class AlertCorrelationRepository(BaseRepository[AlertCorrelation]):
    """CRUD plus lookup for :class:`AlertCorrelation`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AlertCorrelation, tenant_scope=tenant_scope)

    async def list_children(self, parent_alert_id: UUID) -> list[AlertCorrelation]:
        """Every alert correlated *to* *parent_alert_id* as its own root cause."""
        stmt = self._base_select().where(AlertCorrelation.parent_alert_id == parent_alert_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_parents(self, child_alert_id: UUID) -> list[AlertCorrelation]:
        """Every alert *child_alert_id* is itself correlated to."""
        stmt = self._base_select().where(AlertCorrelation.child_alert_id == child_alert_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_edge(
        self, parent_alert_id: UUID, child_alert_id: UUID
    ) -> AlertCorrelation | None:
        """Return the existing edge between two alerts, if any.

        Lets the correlation engine stay idempotent -- re-running
        correlation over the same window must not register the same
        edge twice.
        """
        stmt = self._base_select().where(
            AlertCorrelation.parent_alert_id == parent_alert_id,
            AlertCorrelation.child_alert_id == child_alert_id,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["AlertCorrelationRepository"]
