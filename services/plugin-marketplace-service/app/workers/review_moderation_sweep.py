"""The review moderation sweep worker.

Recomputes every reviewed plugin's own rating aggregate from its raw
review rows -- a self-healing consistency sweep, so ``plugin_ratings``
never permanently drifts from ``plugin_reviews`` even if a direct
``recompute_rating`` call is ever missed (a failed request between
``PluginReviewService.remove``'s two writes, a row edited directly in
the database, etc.). Also surfaces the current flagged-review queue
depth for moderator visibility -- there is no automated content-policy
engine to *decide* moderation outcomes here (that stays a human call via
``POST /plugins/installations/permissions/{grant_id}/...``-style
endpoints in ``app/api/``), so this worker's own honest job is
recomputation and visibility, not judgment. **Leader-elected** through
``shared_core.scheduler`` -- see :mod:`app.workers.registrar`.

**One session per plugin.** A failure recomputing one plugin's own
rating must not poison the transaction the next plugin's own
recomputation needs.
"""

from __future__ import annotations

from uuid import UUID

from shared_core.logging.logger import get_logger
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.review import PluginReview
from app.repositories.review import PluginRatingRepository, PluginReviewRepository
from app.services.review import PluginReviewService

logger = get_logger("app.workers.review_moderation_sweep")


class ReviewModerationSweepWorker:
    """Recomputes rating aggregates and reports the flagged-review queue depth."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], *, max_plugins_per_tick: int = 500
    ) -> None:
        self._session_factory = session_factory
        self._max_plugins_per_tick = max_plugins_per_tick

    async def run_job(self, _job: object) -> None:
        """Entry point matching ``shared_core.scheduler``'s own ``JobFn``."""
        await self.tick()

    async def tick(self) -> int:
        """Recompute every reviewed plugin's rating; returns how many succeeded."""
        plugin_ids = await self._reviewed_plugins()
        recomputed = 0
        for plugin_id in plugin_ids:
            if await self._recompute_one(plugin_id):
                recomputed += 1
        flagged_count = await self._flagged_count()
        logger.info(
            "Review moderation sweep complete.",
            extra={
                "extra_fields": {
                    "plugins": len(plugin_ids),
                    "recomputed": recomputed,
                    "flagged_pending_moderation": flagged_count,
                }
            },
        )
        return recomputed

    async def _reviewed_plugins(self) -> list[UUID]:
        async with self._session_factory() as session:
            statement = select(distinct(PluginReview.plugin_id)).limit(self._max_plugins_per_tick)
            result = await session.execute(statement)
            return [row for row in result.scalars().all() if row is not None]

    async def _recompute_one(self, plugin_id: UUID) -> bool:
        try:
            async with self._session_factory() as session:
                reviews_repo = PluginReviewRepository(session)
                one_review = next(iter(await reviews_repo.list_all_for_plugin(plugin_id)), None)
                if one_review is None:
                    return False
                service = PluginReviewService(reviews_repo, PluginRatingRepository(session))
                await service.recompute_rating(one_review.organization_id, plugin_id)
                await session.commit()
            return True
        except Exception as exc:
            logger.warning(
                "A plugin rating recomputation failed; the rest of the sweep continues.",
                extra={"extra_fields": {"plugin_id": str(plugin_id), "error": str(exc)}},
            )
            return False

    async def _flagged_count(self) -> int:
        async with self._session_factory() as session:
            rows = await PluginReviewRepository(session).list_pending_moderation(limit=100_000)
            return len(rows)


__all__ = ["ReviewModerationSweepWorker"]
