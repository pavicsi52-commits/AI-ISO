"""Repository for :class:`app.models.project_statistics.ProjectStatistics`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_statistics import ProjectStatistics


class ProjectStatisticsRepository(BaseRepository[ProjectStatistics]):
    """CRUD plus lookup for :class:`ProjectStatistics`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProjectStatistics, tenant_scope=tenant_scope)

    async def get_for_project(self, project_id: UUID) -> ProjectStatistics | None:
        """Return *project_id*'s last-computed usage snapshot, or ``None``."""
        stmt = self._base_select().where(ProjectStatistics.project_id == project_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["ProjectStatisticsRepository"]
