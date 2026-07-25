"""Repository for :class:`app.models.automation_rollback.AutomationRollback`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_rollback import AutomationRollback


class AutomationRollbackRepository(BaseRepository[AutomationRollback]):
    """CRUD plus lookup for :class:`AutomationRollback`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AutomationRollback, tenant_scope=tenant_scope)

    async def list_for_execution(self, execution_id: UUID) -> list[AutomationRollback]:
        """Every rollback recorded for *execution_id*, newest first."""
        stmt = (
            self._base_select()
            .where(AutomationRollback.execution_id == execution_id)
            .order_by(desc(AutomationRollback.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["AutomationRollbackRepository"]
