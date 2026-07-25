"""Repository for :class:`app.models.project_preferences.ProjectPreferences`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_preferences import ProjectPreferences


class ProjectPreferencesRepository(BaseRepository[ProjectPreferences]):
    """CRUD plus lookup for :class:`ProjectPreferences`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProjectPreferences, tenant_scope=tenant_scope)

    async def get_for_project(self, project_id: UUID) -> ProjectPreferences | None:
        """Return *project_id*'s preferences, or ``None``."""
        stmt = self._base_select().where(ProjectPreferences.project_id == project_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()


__all__ = ["ProjectPreferencesRepository"]
