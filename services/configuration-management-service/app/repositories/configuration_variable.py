"""Repository for :class:`app.models.configuration_variable.ConfigurationVariable`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration_variable import ConfigurationVariable
from app.models.enums import VariableScope


class ConfigurationVariableRepository(BaseRepository[ConfigurationVariable]):
    """CRUD plus lookup for :class:`ConfigurationVariable`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConfigurationVariable, tenant_scope=tenant_scope)

    async def list_for_scope(
        self, organization_id: UUID, scope: VariableScope, *, scope_ref_id: UUID | None = None
    ) -> list[ConfigurationVariable]:
        """Every variable at *scope* for *organization_id*, optionally
        narrowed to a specific *scope_ref_id* (an environment or asset id).
        """
        stmt = self._base_select().where(
            ConfigurationVariable.organization_id == organization_id,
            ConfigurationVariable.scope == scope,
        )
        if scope_ref_id is not None:
            stmt = stmt.where(ConfigurationVariable.scope_ref_id == scope_ref_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_key(
        self,
        organization_id: UUID,
        scope: VariableScope,
        scope_ref_id: UUID | None,
        key: str,
    ) -> ConfigurationVariable | None:
        """Return the single variable matching *scope*/*scope_ref_id*/*key*, or ``None``."""
        stmt = self._base_select().where(
            ConfigurationVariable.organization_id == organization_id,
            ConfigurationVariable.scope == scope,
            ConfigurationVariable.scope_ref_id == scope_ref_id,
            ConfigurationVariable.key == key,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["ConfigurationVariableRepository"]
