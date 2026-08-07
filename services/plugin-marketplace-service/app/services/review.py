"""Plugin reviews and rolled-up ratings (docs/059 "REVIEWS & RATINGS")."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from shared_core.exceptions.validation import ValidationError

from app.models.enums import ReviewStatus
from app.models.review import PluginRating, PluginReview
from app.repositories.review import PluginRatingRepository, PluginReviewRepository

_MIN_RATING = 1
_MAX_RATING = 5


class PluginReviewService:
    """Submits, moderates, and rolls reviews up into a plugin's own rating aggregate."""

    def __init__(self, reviews: PluginReviewRepository, ratings: PluginRatingRepository) -> None:
        self._reviews = reviews
        self._ratings = ratings

    async def submit(
        self,
        organization_id: UUID,
        plugin_id: UUID,
        *,
        reviewer_id: str,
        rating: int,
        title: str | None = None,
        body: str | None = None,
        installed_version_number: str | None = None,
        verified_install: bool = False,
    ) -> PluginReview:
        """Submit a review, or update the reviewer's own existing one.

        Raises:
            ValidationError: If *rating* is outside ``1..5``.
        """
        if not (_MIN_RATING <= rating <= _MAX_RATING):
            raise ValidationError(f"Rating must be between {_MIN_RATING} and {_MAX_RATING}.")

        existing = await self._reviews.get_by_reviewer(plugin_id, reviewer_id)
        if existing is not None:
            existing.rating = rating
            existing.title = title
            existing.body = body
            existing.installed_version_number = installed_version_number
            existing.verified_install = verified_install
            existing.status = ReviewStatus.PUBLISHED
            review = await self._reviews.update(existing)
        else:
            review = await self._reviews.create(
                PluginReview(
                    organization_id=organization_id,
                    plugin_id=plugin_id,
                    reviewer_id=reviewer_id,
                    rating=rating,
                    title=title,
                    body=body,
                    installed_version_number=installed_version_number,
                    verified_install=verified_install,
                    status=ReviewStatus.PUBLISHED,
                )
            )
        await self.recompute_rating(organization_id, plugin_id)
        return review

    async def flag(
        self, review_id: UUID, *, reason: str, moderated_by: str | None = None
    ) -> PluginReview:
        """Flag a review for moderation."""
        review = await self._reviews.require_by_id(review_id)
        review.status = ReviewStatus.FLAGGED
        review.flagged_reason = reason
        review.moderated_by = moderated_by
        review.moderated_at = datetime.now(UTC)
        return await self._reviews.update(review)

    async def remove(self, review_id: UUID, *, moderated_by: str | None = None) -> PluginReview:
        """Remove a flagged review, and roll its plugin's own rating back down."""
        review = await self._reviews.require_by_id(review_id)
        review.status = ReviewStatus.REMOVED
        review.moderated_by = moderated_by
        review.moderated_at = datetime.now(UTC)
        review = await self._reviews.update(review)
        await self.recompute_rating(review.organization_id, review.plugin_id)
        return review

    async def respond(self, review_id: UUID, *, response: str) -> PluginReview:
        """Record a publisher's own response to a review."""
        review = await self._reviews.require_by_id(review_id)
        review.publisher_response = response
        review.publisher_responded_at = datetime.now(UTC)
        return await self._reviews.update(review)

    async def list_published(
        self, plugin_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> list[PluginReview]:
        """A plugin's own published reviews, newest first."""
        return await self._reviews.list_published_for_plugin(plugin_id, limit=limit, offset=offset)

    async def get_rating(self, plugin_id: UUID) -> PluginRating | None:
        """A plugin's own rating aggregate, if computed yet."""
        return await self._ratings.get_for_plugin(plugin_id)

    async def recompute_rating(self, organization_id: UUID, plugin_id: UUID) -> PluginRating:
        """Recompute a plugin's own rating aggregate from every published review."""
        published = [
            review
            for review in await self._reviews.list_all_for_plugin(plugin_id)
            if review.status == ReviewStatus.PUBLISHED
        ]
        counts = dict.fromkeys(range(_MIN_RATING, _MAX_RATING + 1), 0)
        for review in published:
            counts[review.rating] = counts.get(review.rating, 0) + 1
        total = len(published)
        average = sum(review.rating for review in published) / total if total else 0.0

        aggregate = await self._ratings.get_for_plugin(plugin_id) or PluginRating(
            organization_id=organization_id, plugin_id=plugin_id
        )
        aggregate.average_rating = average
        aggregate.review_count = total
        aggregate.rating_1_count = counts.get(1, 0)
        aggregate.rating_2_count = counts.get(2, 0)
        aggregate.rating_3_count = counts.get(3, 0)
        aggregate.rating_4_count = counts.get(4, 0)
        aggregate.rating_5_count = counts.get(5, 0)
        aggregate.recalculated_at = datetime.now(UTC)
        if aggregate.id is None:
            return await self._ratings.create(aggregate)
        return await self._ratings.update(aggregate)

    async def list_pending_moderation(self, *, limit: int = 200) -> list[PluginReview]:
        """Every review flagged for the moderation sweep to act on."""
        return await self._reviews.list_pending_moderation(limit=limit)


__all__ = ["PluginReviewService"]
