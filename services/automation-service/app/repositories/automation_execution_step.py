"""Repository for :class:`app.models.automation_execution_step.AutomationExecutionStep`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_execution_step import AutomationExecutionStep


class AutomationExecutionStepRepository(BaseRepository[AutomationExecutionStep]):
    """CRUD plus lookup for :class:`AutomationExecutionStep`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AutomationExecutionStep, tenant_scope=tenant_scope)

    async def list_for_execution(self, execution_id: UUID) -> list[AutomationExecutionStep]:
        """Every step recorded for *execution_id*, in declared order."""
        stmt = (
            self._base_select()
            .where(AutomationExecutionStep.execution_id == execution_id)
            .order_by(asc(AutomationExecutionStep.step_index))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AutomationExecutionStepRepository"]
