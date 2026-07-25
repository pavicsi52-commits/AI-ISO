"""Repository for :class:`app.models.configuration_assignment.ConfigurationAssignment`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration_assignment import ConfigurationAssignment


class ConfigurationAssignmentRepository(BaseRepository[ConfigurationAssignment]):
    """CRUD plus lookup for :class:`ConfigurationAssignment`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConfigurationAssignment, tenant_scope=tenant_scope)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationAssignment]:
        """Every managed asset assigned to *profile_id*."""
        stmt = self._base_select().where(ConfigurationAssignment.profile_id == profile_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[ConfigurationAssignment]:
        """Every configuration profile assigned to *managed_asset_id*."""
        stmt = self._base_select().where(
            ConfigurationAssignment.managed_asset_id == managed_asset_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_profile_and_asset(
        self, profile_id: UUID, managed_asset_id: UUID
    ) -> ConfigurationAssignment | None:
        """Return the assignment linking *profile_id* to *managed_asset_id*, or ``None``."""
        stmt = self._base_select().where(
            ConfigurationAssignment.profile_id == profile_id,
            ConfigurationAssignment.managed_asset_id == managed_asset_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["ConfigurationAssignmentRepository"]
