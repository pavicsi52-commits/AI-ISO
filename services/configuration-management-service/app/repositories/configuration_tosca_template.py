"""Repository for :class:`app.models.configuration_tosca_template.ConfigurationToscaTemplate`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration_tosca_template import ConfigurationToscaTemplate


class ConfigurationToscaTemplateRepository(BaseRepository[ConfigurationToscaTemplate]):
    """CRUD plus lookup for :class:`ConfigurationToscaTemplate`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConfigurationToscaTemplate, tenant_scope=tenant_scope)

    async def list_for_profile(self, profile_id: UUID) -> list[ConfigurationToscaTemplate]:
        """Every TOSCA template component backing *profile_id*."""
        stmt = self._base_select().where(ConfigurationToscaTemplate.profile_id == profile_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConfigurationToscaTemplateRepository"]
