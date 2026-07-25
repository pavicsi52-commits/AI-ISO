"""Repository for :class:`app.models.configuration_baseline.ConfigurationBaseline`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration_baseline import ConfigurationBaseline
from app.models.enums import BaselineType


class ConfigurationBaselineRepository(BaseRepository[ConfigurationBaseline]):
    """CRUD plus lookup for :class:`ConfigurationBaseline`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConfigurationBaseline, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, baseline_type: BaselineType | None = None
    ) -> list[ConfigurationBaseline]:
        """Every baseline belonging to *organization_id*, optionally
        narrowed to a single *baseline_type*.
        """
        stmt = self._base_select().where(ConfigurationBaseline.organization_id == organization_id)
        if baseline_type is not None:
            stmt = stmt.where(ConfigurationBaseline.baseline_type == baseline_type)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationBaseline]:
        """Every baseline associated with *profile_id* ("Version History")."""
        stmt = self._base_select().where(ConfigurationBaseline.profile_id == profile_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConfigurationBaselineRepository"]
