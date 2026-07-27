"""Playbook draft reviews. Per docs/041 "APPROVALS" "Support": Draft Review."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.enums import ReviewStatus
from app.models.playbook_review import PlaybookReview
from app.repositories.playbook import PlaybookRepository
from app.repositories.playbook_review import PlaybookReviewRepository


class PlaybookReviewService:
    """Requests and decides playbook draft reviews."""

    def __init__(self, reviews: PlaybookReviewRepository, playbooks: PlaybookRepository) -> None:
        self._reviews = reviews
        self._playbooks = playbooks

    async def get_by_id(self, review_id: UUID) -> PlaybookReview:
        """Return the review identified by *review_id*.

        Raises:
            NotFoundError: If no such review exists.
        """
        return await self._reviews.require_by_id(review_id)

    async def list_for_playbook(self, playbook_id: UUID) -> list[PlaybookReview]:
        """Every review recorded for *playbook_id*."""
        return await self._reviews.list_for_playbook(playbook_id)

    async def request(
        self, playbook_id: UUID, *, version_id: UUID | None, reviewer_id: UUID | None
    ) -> PlaybookReview:
        """Request a new draft review ("Draft Review").

        Raises:
            NotFoundError: If *playbook_id* does not exist.
        """
        playbook = await self._playbooks.require_by_id(playbook_id)
        return await self._reviews.create(
            PlaybookReview(
                organization_id=playbook.organization_id,
                playbook_id=playbook_id,
                version_id=version_id,
                reviewer_id=reviewer_id,
                status=ReviewStatus.PENDING,
            )
        )

    async def decide(
        self, review_id: UUID, *, status: ReviewStatus, comments: str | None
    ) -> PlaybookReview:
        """Record a review decision."""
        review = await self.get_by_id(review_id)
        review.status = status
        review.comments = comments
        review.reviewed_at = datetime.now(UTC)
        return await self._reviews.update(review)


__all__ = ["PlaybookReviewService"]
