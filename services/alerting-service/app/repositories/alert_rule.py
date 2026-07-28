"""Repository for :class:`app.models.alert_rule.AlertRule`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_rule import AlertRule
from app.models.enums import AlertSource


class AlertRuleRepository(BaseRepository[AlertRule]):
    """CRUD plus lookup for :class:`AlertRule`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AlertRule, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[AlertRule]:
        """Every alert rule belonging to *organization_id*."""
        stmt = self._base_select().where(AlertRule.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_enabled_for_source(
        self, organization_id: UUID, source: AlertSource
    ) -> list[AlertRule]:
        """Every enabled rule matching *source*, for evaluating an incoming event."""
        stmt = self._base_select().where(
            AlertRule.organization_id == organization_id,
            AlertRule.source == source,
            AlertRule.enabled.is_(True),
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AlertRuleRepository"]
