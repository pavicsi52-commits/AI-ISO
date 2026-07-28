"""Repository for :class:`app.models.monitoring_retention.MonitoringRetention`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import MetricType
from app.models.monitoring_retention import MonitoringRetention


class MonitoringRetentionRepository(BaseRepository[MonitoringRetention]):
    """CRUD plus lookup for :class:`MonitoringRetention`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MonitoringRetention, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringRetention]:
        """Every retention policy belonging to *organization_id*."""
        stmt = self._base_select().where(MonitoringRetention.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_metric_type(
        self, organization_id: UUID, metric_type: MetricType
    ) -> MonitoringRetention | None:
        """Return the policy specific to *metric_type*, or ``None`` if none is configured."""
        stmt = self._base_select().where(
            MonitoringRetention.organization_id == organization_id,
            MonitoringRetention.metric_type == metric_type,
            MonitoringRetention.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_default_for_org(self, organization_id: UUID) -> MonitoringRetention | None:
        """Return *organization_id*'s own default policy (``metric_type IS NULL``), if any."""
        stmt = self._base_select().where(
            MonitoringRetention.organization_id == organization_id,
            MonitoringRetention.metric_type.is_(None),
            MonitoringRetention.is_active.is_(True),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["MonitoringRetentionRepository"]
