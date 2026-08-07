"""``plugin_reviews`` and ``plugin_ratings`` repositories."""

from __future__ import annotations

from uuid import UUID

from shared_core.database.repository import BaseRepository
from shared_core.database.tenant import TenantScope
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReviewStatus
from app.models.review import PluginRating, PluginReview


class PluginReviewRepository(BaseRepository[PluginReview]):
    """Public star-rating + text reviews for a plugin."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PluginReview, tenant_scope=tenant_scope)

    async def list_published_for_plugin(
        self, plugin_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> list[PluginReview]:
        """A plugin's own published reviews, newest first."""
        stmt = (
            self._base_select()
            .where(PluginReview.plugin_id == plugin_id)
            .where(PluginReview.status == ReviewStatus.PUBLISHED)
            .order_by(PluginReview.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_for_plugin(self, plugin_id: UUID) -> list[PluginReview]:
        """Every review for a plugin regardless of status -- for aggregate rollup."""
        stmt = self._base_select().where(PluginReview.plugin_id == plugin_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_reviewer(self, plugin_id: UUID, reviewer_id: str) -> PluginReview | None:
        """One reviewer's own review of a plugin, if they've already left one."""
        stmt = (
            self._base_select()
            .where(PluginReview.plugin_id == plugin_id)
            .where(PluginReview.reviewer_id == reviewer_id)
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def list_pending_moderation(self, *, limit: int = 200) -> list[PluginReview]:
        """Every review flagged for the moderation sweep to act on."""
        stmt = (
            self._base_select()
            .where(PluginReview.status == ReviewStatus.FLAGGED)
            .order_by(PluginReview.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())


class PluginRatingRepository(BaseRepository[PluginRating]):
    """A plugin's own rolled-up rating aggregate."""

    def __init__(self, session: AsyncSession, *, tenant_scope: TenantScope | None = None) -> None:
        super().__init__(session, PluginRating, tenant_scope=tenant_scope)

    async def get_for_plugin(self, plugin_id: UUID) -> PluginRating | None:
        """The rating aggregate row for one plugin, if it has been computed yet."""
        stmt = self._base_select().where(PluginRating.plugin_id == plugin_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()


__all__ = ["PluginRatingRepository", "PluginReviewRepository"]
