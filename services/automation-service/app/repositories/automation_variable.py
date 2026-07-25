"""Repository for :class:`app.models.automation_variable.AutomationVariable`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_variable import AutomationVariable
from app.models.enums import VariableScope


class AutomationVariableRepository(BaseRepository[AutomationVariable]):
    """CRUD plus lookup for :class:`AutomationVariable`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, AutomationVariable, tenant_scope=tenant_scope)

    async def list_for_scope(
        self, organization_id: UUID, scope: VariableScope, *, scope_ref_id: UUID | None = None
    ) -> list[AutomationVariable]:
        """Every variable at *scope* for *organization_id*, optionally
        narrowed to a specific *scope_ref_id* (a job or execution id).
        """
        stmt = self._base_select().where(
            AutomationVariable.organization_id == organization_id,
            AutomationVariable.scope == scope,
        )
        if scope_ref_id is not None:
            stmt = stmt.where(AutomationVariable.scope_ref_id == scope_ref_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_key(
        self,
        organization_id: UUID,
        scope: VariableScope,
        scope_ref_id: UUID | None,
        key: str,
    ) -> AutomationVariable | None:
        """Return the single variable matching *scope*/*scope_ref_id*/*key*, or ``None``."""
        stmt = self._base_select().where(
            AutomationVariable.organization_id == organization_id,
            AutomationVariable.scope == scope,
            AutomationVariable.scope_ref_id == scope_ref_id,
            AutomationVariable.key == key,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["AutomationVariableRepository"]
