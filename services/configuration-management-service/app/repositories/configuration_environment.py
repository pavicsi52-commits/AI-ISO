"""Repository for :class:`app.models.configuration_environment.ConfigurationEnvironment`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration_environment import ConfigurationEnvironment


class ConfigurationEnvironmentRepository(BaseRepository[ConfigurationEnvironment]):
    """CRUD plus lookup for :class:`ConfigurationEnvironment`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConfigurationEnvironment, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[ConfigurationEnvironment]:
        """Every environment definition for *organization_id*."""
        stmt = self._base_select().where(
            ConfigurationEnvironment.organization_id == organization_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(
        self, organization_id: UUID, name: str
    ) -> ConfigurationEnvironment | None:
        """Return *organization_id*'s environment named *name*, or ``None``."""
        stmt = self._base_select().where(
            ConfigurationEnvironment.organization_id == organization_id,
            ConfigurationEnvironment.name == name,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["ConfigurationEnvironmentRepository"]
