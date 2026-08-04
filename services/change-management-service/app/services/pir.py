"""Post-implementation reviews: authoring, action items, and approval.

A PIR's lifecycle -- draft, review, approval -- is deliberately linear
and one-way except for the review step, which can send it back to
draft. There is no reopening an approved review: a correction to an
approved document is a new note added to it, the same reasoning
Prompt 052 applies to a published postmortem.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.events.change_events import SOURCE_SERVICE, PirCompletedEvent
from app.models.enums import (
    ChangeStatus,
    ChangeTaskStatus,
    PirStatus,
    change_task_status_of,
    pir_status_of,
)
from app.models.pir import ChangePostReview, ChangePostReviewActionItem
from app.repositories.change import ChangeRequestRepository
from app.repositories.pir import ChangePostReviewActionItemRepository, ChangePostReviewRepository
from app.types import EventPublisher

logger = get_logger("app.services.pir")

_REVIEWABLE_STATUSES = frozenset(
    {ChangeStatus.COMPLETED, ChangeStatus.ROLLED_BACK, ChangeStatus.CLOSED}
)
"""A PIR reviews what actually happened during implementation, so it is
only startable once a change reached one of these -- ``CANCELLED`` and
``REJECTED`` changes never implemented anything to review."""

_ALLOWED_TRANSITIONS: dict[PirStatus, frozenset[PirStatus]] = {
    PirStatus.DRAFT: frozenset({PirStatus.IN_REVIEW}),
    PirStatus.IN_REVIEW: frozenset({PirStatus.DRAFT, PirStatus.APPROVED}),
    PirStatus.APPROVED: frozenset(),
}


class PirService:
    """Post-implementation reviews: authoring, action items, review, approval."""

    def __init__(
        self,
        reviews: ChangePostReviewRepository,
        action_items: ChangePostReviewActionItemRepository,
        changes: ChangeRequestRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._reviews = reviews
        self._action_items = action_items
        self._changes = changes
        self._publish = publish_event

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def start(
        self, organization_id: UUID, change_id: UUID, *, owner_id: str | None = None
    ) -> ChangePostReview:
        """Begin a post-implementation review for one change.

        Raises:
            ValidationError: If the change has not completed or been
                rolled back yet -- a review written before the change is
                over is documenting something still in motion.
            ConflictError: If one already exists for this change.
        """
        stored = await self._changes.require_in_org(organization_id, change_id)
        if stored.status not in {str(one) for one in _REVIEWABLE_STATUSES}:
            raise ValidationError(
                f"{stored.reference} is {stored.status!s}; a PIR cannot begin until it has "
                "completed or been rolled back."
            )
        if await self._reviews.get_for_change(organization_id, change_id) is not None:
            raise ConflictError(
                f"A post-implementation review already exists for {stored.reference}."
            )

        return await self._reviews.create(
            ChangePostReview(
                organization_id=organization_id,
                change_id=change_id,
                status=PirStatus.DRAFT,
                owner_id=owner_id,
            )
        )

    async def update_content(
        self, organization_id: UUID, review_id: UUID, **fields: Any
    ) -> ChangePostReview:
        """Edit a review's content.

        Raises:
            ConflictError: If it has already been approved.
        """
        row = await self._reviews.require_in_org(organization_id, review_id)
        if pir_status_of(row.status) is PirStatus.APPROVED:
            raise ConflictError(f"PIR {review_id} is approved and cannot be edited.")
        for field, value in fields.items():
            setattr(row, field, value)
        return await self._reviews.update(row)

    async def add_action_item(
        self,
        organization_id: UUID,
        review_id: UUID,
        *,
        title: str,
        description: str | None = None,
        owner_id: str | None = None,
        due_at: datetime | None = None,
    ) -> ChangePostReviewActionItem:
        """Commit a follow-up action from a review."""
        await self._reviews.require_in_org(organization_id, review_id)
        return await self._action_items.create(
            ChangePostReviewActionItem(
                organization_id=organization_id,
                post_review_id=review_id,
                title=title,
                description=description,
                status=ChangeTaskStatus.PENDING,
                owner_id=owner_id,
                due_at=due_at,
            )
        )

    async def complete_action_item(
        self, organization_id: UUID, action_item_id: UUID
    ) -> ChangePostReviewActionItem:
        """Mark an action item done."""
        row = await self._action_items.require_in_org(organization_id, action_item_id)
        row.status = ChangeTaskStatus.COMPLETED
        row.completed_at = datetime.now(UTC)
        return await self._action_items.update(row)

    async def transition(
        self,
        organization_id: UUID,
        review_id: UUID,
        *,
        target: PirStatus,
        actor_id: str | None = None,
    ) -> ChangePostReview:
        """Move a review through its lifecycle.

        Raises:
            ValidationError: If *target* is not reachable from the
                review's current status, or approval is requested while
                an action item remains unowned.
        """
        moment = datetime.now(UTC)
        row = await self._reviews.require_in_org(organization_id, review_id)
        current = pir_status_of(row.status)
        if target not in _ALLOWED_TRANSITIONS[current]:
            allowed = (
                ", ".join(sorted(str(one) for one in _ALLOWED_TRANSITIONS[current])) or "nothing"
            )
            raise ValidationError(
                f"A PIR that is {current!s} cannot move to {target!s}. "
                f"Allowed from here: {allowed}."
            )

        if target is PirStatus.APPROVED:
            items = await self._action_items.list_for_review(organization_id, review_id)
            unowned = [
                one
                for one in items
                if change_task_status_of(one.status) is not ChangeTaskStatus.SKIPPED
                and one.owner_id is None
            ]
            if unowned:
                raise ValidationError(
                    f"{len(unowned)} action item(s) have no owner. A commitment nobody owns "
                    "is not a commitment, and approval is where that gets caught."
                )
            row.approved_by = actor_id
            row.approved_at = moment

        row.status = target
        updated = await self._reviews.update(row)

        if target is PirStatus.APPROVED:
            await self._publish_event(
                PirCompletedEvent(
                    source_service=SOURCE_SERVICE,
                    payload={
                        "organization_id": str(organization_id),
                        "review_id": str(review_id),
                        "change_id": str(row.change_id),
                    },
                )
            )
        return updated

    async def get(self, organization_id: UUID, review_id: UUID) -> ChangePostReview:
        """One review.

        Raises:
            NotFoundError: If it does not exist here.
        """
        return await self._reviews.require_in_org(organization_id, review_id)

    async def get_for_change(
        self, organization_id: UUID, change_id: UUID
    ) -> ChangePostReview | None:
        """The review for one change, if one has been started."""
        return await self._reviews.get_for_change(organization_id, change_id)

    async def action_items(
        self, organization_id: UUID, review_id: UUID
    ) -> list[ChangePostReviewActionItem]:
        """Every action item committed in one review."""
        await self._reviews.require_in_org(organization_id, review_id)
        return await self._action_items.list_for_review(organization_id, review_id)

    async def open_action_items_for(
        self, organization_id: UUID, owner_id: str
    ) -> list[ChangePostReviewActionItem]:
        """One person's outstanding commitments across every PIR."""
        return await self._action_items.list_open_for_owner(organization_id, owner_id)


__all__ = ["PirService"]
