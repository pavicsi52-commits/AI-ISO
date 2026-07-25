"""Repository for :class:`app.models.project_label.ProjectLabel`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_label import ProjectLabel


class ProjectLabelRepository(BaseRepository[ProjectLabel]):
    """CRUD plus lookup for :class:`ProjectLabel`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProjectLabel, tenant_scope=tenant_scope)

    async def get_by_key(self, project_id: UUID, key: str) -> ProjectLabel | None:
        """Return the label identified by *key* on *project_id*, or ``None``."""
        stmt = self._base_select().where(
            ProjectLabel.project_id == project_id, ProjectLabel.key == key
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_project(self, project_id: UUID) -> list[ProjectLabel]:
        """Every label assigned to *project_id*."""
        stmt = self._base_select().where(ProjectLabel.project_id == project_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ProjectLabelRepository"]
