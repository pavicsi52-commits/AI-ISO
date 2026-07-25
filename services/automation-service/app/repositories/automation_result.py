"""Repository for :class:`app.models.automation_result.AutomationResult`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_result import AutomationResult


class AutomationResultRepository(BaseRepository[AutomationResult]):
    """CRUD plus lookup for :class:`AutomationResult`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AutomationResult, tenant_scope=tenant_scope)

    async def get_for_execution(self, execution_id: UUID) -> AutomationResult | None:
        """Return *execution_id*'s final result summary, or ``None``."""
        stmt = self._base_select().where(AutomationResult.execution_id == execution_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["AutomationResultRepository"]
