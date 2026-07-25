"""Repository for :class:`app.models.project_template.ProjectTemplate`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_template import ProjectTemplate


class ProjectTemplateRepository(BaseRepository[ProjectTemplate]):
    """CRUD plus lookup for :class:`ProjectTemplate`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProjectTemplate, tenant_scope=tenant_scope)

    async def list_for_org(self, organization_id: UUID) -> list[ProjectTemplate]:
        """Every template available to *organization_id*."""
        stmt = self._base_select().where(ProjectTemplate.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name_version(
        self, organization_id: UUID, name: str, template_version: str
    ) -> ProjectTemplate | None:
        """Return the template identified by *name*/*template_version*, or ``None``."""
        stmt = self._base_select().where(
            ProjectTemplate.organization_id == organization_id,
            ProjectTemplate.name == name,
            ProjectTemplate.template_version == template_version,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["ProjectTemplateRepository"]
