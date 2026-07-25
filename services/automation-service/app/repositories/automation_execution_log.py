"""Repository for :class:`app.models.automation_execution_log.AutomationExecutionLog`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_execution_log import AutomationExecutionLog


class AutomationExecutionLogRepository(BaseRepository[AutomationExecutionLog]):
    """CRUD plus lookup for :class:`AutomationExecutionLog`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AutomationExecutionLog, tenant_scope=tenant_scope)

    async def list_for_execution(self, execution_id: UUID) -> list[AutomationExecutionLog]:
        """Every log line recorded for *execution_id*, oldest first."""
        stmt = (
            self._base_select()
            .where(AutomationExecutionLog.execution_id == execution_id)
            .order_by(asc(AutomationExecutionLog.logged_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AutomationExecutionLogRepository"]
