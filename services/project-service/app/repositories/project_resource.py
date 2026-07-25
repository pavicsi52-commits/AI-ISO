"""Repository for :class:`app.models.project_resource.ProjectResource`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ProjectResourceType
from app.models.project_resource import ProjectResource


class ProjectResourceRepository(BaseRepository[ProjectResource]):
    """CRUD plus lookup for :class:`ProjectResource`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProjectResource, tenant_scope=tenant_scope)

    async def get_by_link(
        self, project_id: UUID, resource_type: ProjectResourceType, resource_id: UUID
    ) -> ProjectResource | None:
        """Return the link identified by *(resource_type, resource_id)* on
        *project_id*, or ``None``.
        """
        stmt = self._base_select().where(
            ProjectResource.project_id == project_id,
            ProjectResource.resource_type == resource_type,
            ProjectResource.resource_id == resource_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_project(self, project_id: UUID) -> list[ProjectResource]:
        """Every resource linked to *project_id*."""
        stmt = self._base_select().where(ProjectResource.project_id == project_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ProjectResourceRepository"]
