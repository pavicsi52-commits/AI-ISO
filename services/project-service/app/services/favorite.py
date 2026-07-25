"""Project favorite management -- no dedicated REST surface in docs/034's
own endpoint list, matching ``app/services/preferences.py``'s identical
scope decision.
"""

from __future__ import annotations

from uuid import UUID

from app.models.project_favorite import ProjectFavorite
from app.repositories.project_favorite import ProjectFavoriteRepository


class ProjectFavoriteService:
    """Marks, lists, and clears a user's favorite projects."""

    def __init__(self, favorites: ProjectFavoriteRepository) -> None:
        self._favorites = favorites

    async def list_for_user(self, user_id: UUID) -> list[ProjectFavorite]:
        """Every project *user_id* has favorited."""
        return await self._favorites.list_for_user(user_id)

    async def mark(
        self, project_id: UUID, user_id: UUID, *, organization_id: UUID
    ) -> ProjectFavorite:
        """Mark *project_id* as a favorite for *user_id* (idempotent)."""
        existing = await self._favorites.get(project_id, user_id)
        if existing is not None:
            return existing
        return await self._favorites.create(
            ProjectFavorite(project_id=project_id, organization_id=organization_id, user_id=user_id)
        )

    async def unmark(self, project_id: UUID, user_id: UUID) -> None:
        """Remove *project_id* from *user_id*'s favorites (a no-op if absent)."""
        existing = await self._favorites.get(project_id, user_id)
        if existing is not None:
            await self._favorites.delete(existing.id)


__all__ = ["ProjectFavoriteService"]
