"""Repository for :class:`app.models.automation_retry_history.AutomationRetryHistory`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import asc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_retry_history import AutomationRetryHistory


class AutomationRetryHistoryRepository(BaseRepository[AutomationRetryHistory]):
    """CRUD plus lookup for :class:`AutomationRetryHistory`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AutomationRetryHistory, tenant_scope=tenant_scope)

    async def list_for_execution(self, execution_id: UUID) -> list[AutomationRetryHistory]:
        """Every retry attempt recorded for *execution_id*, in attempt order."""
        stmt = (
            self._base_select()
            .where(AutomationRetryHistory.execution_id == execution_id)
            .order_by(asc(AutomationRetryHistory.attempt_number))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AutomationRetryHistoryRepository"]
