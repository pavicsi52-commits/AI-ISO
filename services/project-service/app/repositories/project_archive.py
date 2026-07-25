"""Repository for :class:`app.models.project_archive.ProjectArchive`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_archive import ProjectArchive


class ProjectArchiveRepository(BaseRepository[ProjectArchive]):
    """CRUD plus lookup for :class:`ProjectArchive`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProjectArchive, tenant_scope=tenant_scope)

    async def list_for_project(self, project_id: UUID) -> list[ProjectArchive]:
        """Every archive event for *project_id*, newest first."""
        stmt = (
            self._base_select()
            .where(ProjectArchive.project_id == project_id)
            .order_by(desc(ProjectArchive.created_at))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_unrestored(self, project_id: UUID) -> ProjectArchive | None:
        """Return *project_id*'s most recent not-yet-restored archive event, or ``None``."""
        stmt = (
            self._base_select()
            .where(ProjectArchive.project_id == project_id, ProjectArchive.restored_at.is_(None))
            .order_by(desc(ProjectArchive.created_at))
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["ProjectArchiveRepository"]
