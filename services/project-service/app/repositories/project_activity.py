"""Repository for :class:`app.models.project_activity.ProjectActivity`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_activity import ProjectActivity


class ProjectActivityRepository(BaseRepository[ProjectActivity]):
    """CRUD plus listing for :class:`ProjectActivity`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProjectActivity, tenant_scope=tenant_scope)

    async def list_recent_for_project(
        self, project_id: UUID, *, limit: int = 50
    ) -> list[ProjectActivity]:
        """The *limit* most recent activity entries for *project_id*, newest first."""
        stmt = (
            self._base_select()
            .where(ProjectActivity.project_id == project_id)
            .order_by(desc(ProjectActivity.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ProjectActivityRepository"]
