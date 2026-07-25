"""Repository for :class:`app.models.project_integration.ProjectIntegration`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_integration import ProjectIntegration


class ProjectIntegrationRepository(BaseRepository[ProjectIntegration]):
    """CRUD plus lookup for :class:`ProjectIntegration`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProjectIntegration, tenant_scope=tenant_scope)

    async def get_by_name(self, project_id: UUID, name: str) -> ProjectIntegration | None:
        """Return the integration identified by *name* on *project_id*, or ``None``."""
        stmt = self._base_select().where(
            ProjectIntegration.project_id == project_id, ProjectIntegration.name == name
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_project(self, project_id: UUID) -> list[ProjectIntegration]:
        """Every integration configured for *project_id*."""
        stmt = self._base_select().where(ProjectIntegration.project_id == project_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ProjectIntegrationRepository"]
