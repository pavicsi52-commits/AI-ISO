"""Repository for :class:`app.models.automation_output.AutomationOutput`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_output import AutomationOutput


class AutomationOutputRepository(BaseRepository[AutomationOutput]):
    """CRUD plus lookup for :class:`AutomationOutput`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AutomationOutput, tenant_scope=tenant_scope)

    async def list_for_execution(self, execution_id: UUID) -> list[AutomationOutput]:
        """Every output captured for *execution_id*."""
        stmt = self._base_select().where(AutomationOutput.execution_id == execution_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_key(self, execution_id: UUID, key: str) -> AutomationOutput | None:
        """Return *execution_id*'s output named *key*, or ``None``."""
        stmt = self._base_select().where(
            AutomationOutput.execution_id == execution_id, AutomationOutput.key == key
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["AutomationOutputRepository"]
