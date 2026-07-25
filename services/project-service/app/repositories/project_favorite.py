"""Repository for :class:`app.models.project_favorite.ProjectFavorite`."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_favorite import ProjectFavorite


class ProjectFavoriteRepository(BaseRepository[ProjectFavorite]):
    """CRUD plus lookup for :class:`ProjectFavorite`."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, ProjectFavorite, tenant_scope=tenant_scope)

    async def get(self, project_id: UUID, user_id: UUID) -> ProjectFavorite | None:
        """Return *user_id*'s favorite marker on *project_id*, or ``None``."""
        stmt = self._base_select().where(
            ProjectFavorite.project_id == project_id, ProjectFavorite.user_id == user_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: UUID) -> list[ProjectFavorite]:
        """Every project *user_id* has favorited."""
        stmt = self._base_select().where(ProjectFavorite.user_id == user_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


__all__ = ["ProjectFavoriteRepository"]
