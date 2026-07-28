"""Repository for :class:`app.models.monitoring_health.MonitoringHealth`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring_health import MonitoringHealth


class MonitoringHealthRepository(BaseRepository[MonitoringHealth]):
    """CRUD plus lookup for :class:`MonitoringHealth`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MonitoringHealth, tenant_scope=tenant_scope)

    async def list_for_target(self, target_id: UUID) -> list[MonitoringHealth]:
        """Every health-check result recorded for *target_id*, most recent first."""
        stmt = (
            self._base_select()
            .where(MonitoringHealth.target_id == target_id)
            .order_by(MonitoringHealth.checked_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_for_target(self, target_id: UUID) -> MonitoringHealth | None:
        """Return *target_id*'s own most recent health-check result, or ``None``."""
        results = await self.list_for_target(target_id)
        return results[0] if results else None


__all__ = ["MonitoringHealthRepository"]
