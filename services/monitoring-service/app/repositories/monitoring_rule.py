"""Repository for :class:`app.models.monitoring_rule.MonitoringRule`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring_rule import MonitoringRule


class MonitoringRuleRepository(BaseRepository[MonitoringRule]):
    """CRUD plus lookup for :class:`MonitoringRule`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, MonitoringRule, tenant_scope=tenant_scope)

    async def list_for_metric(self, metric_id: UUID) -> list[MonitoringRule]:
        """Every active rule scoped to *metric_id*."""
        stmt = self._base_select().where(
            MonitoringRule.metric_id == metric_id, MonitoringRule.is_active.is_(True)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_org(self, organization_id: UUID) -> list[MonitoringRule]:
        """Every rule belonging to *organization_id*."""
        stmt = self._base_select().where(MonitoringRule.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["MonitoringRuleRepository"]
