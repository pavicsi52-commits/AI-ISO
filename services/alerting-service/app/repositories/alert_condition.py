"""Repository for :class:`app.models.alert_condition.AlertCondition`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert_condition import AlertCondition


class AlertConditionRepository(BaseRepository[AlertCondition]):
    """CRUD plus lookup for :class:`AlertCondition`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AlertCondition, tenant_scope=tenant_scope)

    async def list_for_rule(self, rule_id: UUID) -> list[AlertCondition]:
        """Every condition attached to *rule_id*, in evaluation order."""
        stmt = (
            self._base_select()
            .where(AlertCondition.rule_id == rule_id)
            .order_by(AlertCondition.sequence.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AlertConditionRepository"]
