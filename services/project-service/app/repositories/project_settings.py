"""Repository for :class:`app.models.project_settings.ProjectSettings`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_settings import ProjectSettings


class ProjectSettingsRepository(BaseRepository[ProjectSettings]):
    """CRUD plus lookup for :class:`ProjectSettings`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProjectSettings, tenant_scope=tenant_scope)

    async def get_for_project(self, project_id: UUID) -> ProjectSettings | None:
        """Return *project_id*'s settings, or ``None``."""
        stmt = self._base_select().where(ProjectSettings.project_id == project_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["ProjectSettingsRepository"]
