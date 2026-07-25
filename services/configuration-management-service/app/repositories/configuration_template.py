"""Repository for :class:`app.models.configuration_template.ConfigurationTemplate`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration_template import ConfigurationTemplate
from app.models.enums import ConfigurationType


class ConfigurationTemplateRepository(BaseRepository[ConfigurationTemplate]):
    """CRUD plus lookup for :class:`ConfigurationTemplate`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ConfigurationTemplate, tenant_scope=tenant_scope)

    async def list_for_org(
        self, organization_id: UUID, *, configuration_type: ConfigurationType | None = None
    ) -> list[ConfigurationTemplate]:
        """Every template belonging to *organization_id*, optionally
        narrowed to a single *configuration_type*.
        """
        stmt = self._base_select().where(ConfigurationTemplate.organization_id == organization_id)
        if configuration_type is not None:
            stmt = stmt.where(ConfigurationTemplate.configuration_type == configuration_type)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ConfigurationTemplateRepository"]
