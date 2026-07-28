"""Repository for :class:`app.models.monitoring_availability.MonitoringAvailability`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring_availability import MonitoringAvailability


class MonitoringAvailabilityRepository(BaseRepository[MonitoringAvailability]):
    """CRUD plus lookup for :class:`MonitoringAvailability`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MonitoringAvailability, tenant_scope=tenant_scope)

    async def list_for_target(self, target_id: UUID) -> list[MonitoringAvailability]:
        """Every availability interval recorded for *target_id*, oldest first."""
        stmt = (
            self._base_select()
            .where(MonitoringAvailability.target_id == target_id)
            .order_by(MonitoringAvailability.started_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_current_for_target(self, target_id: UUID) -> MonitoringAvailability | None:
        """Return *target_id*'s own still-open interval (``ended_at IS NULL``), if any."""
        stmt = self._base_select().where(
            MonitoringAvailability.target_id == target_id,
            MonitoringAvailability.ended_at.is_(None),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["MonitoringAvailabilityRepository"]
