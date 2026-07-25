"""Repository for :class:`app.models.project_metadata.ProjectMetadataEntry`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_metadata import ProjectMetadataEntry


class ProjectMetadataRepository(BaseRepository[ProjectMetadataEntry]):
    """CRUD plus lookup for :class:`ProjectMetadataEntry`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProjectMetadataEntry, tenant_scope=tenant_scope)

    async def get_by_key(self, project_id: UUID, key: str) -> ProjectMetadataEntry | None:
        """Return the metadata entry identified by *key* on *project_id*, or ``None``."""
        stmt = self._base_select().where(
            ProjectMetadataEntry.project_id == project_id, ProjectMetadataEntry.key == key
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_project(self, project_id: UUID) -> list[ProjectMetadataEntry]:
        """Every metadata entry for *project_id*."""
        stmt = self._base_select().where(ProjectMetadataEntry.project_id == project_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ProjectMetadataRepository"]
