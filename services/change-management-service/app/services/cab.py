"""Scheduling and running a Change Advisory Board review.

Wraps ``app/cab/engine.py`` with the database, the clock, and the
change lifecycle: closing a meeting is what actually resolves a
``CAB_REVIEW`` change one way or the other.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.conflict import ConflictError
from shared_core.logging.logger import get_logger

from app.cab.engine import tally
from app.changes.engine import validate_transition
from app.events.change_events import SOURCE_SERVICE, CabApprovedEvent
from app.models.cab import ChangeCab, ChangeCabVote
from app.models.enums import (
    CabMeetingStatus,
    CabVote,
    ChangeStatus,
    cab_meeting_status_of,
    cab_vote_of,
    change_status_of,
)
from app.notifications.change_notifications import ChangeNotificationService
from app.repositories.cab import ChangeCabRepository, ChangeCabVoteRepository
from app.repositories.change import ChangeRequestRepository
from app.types import EventPublisher

logger = get_logger("app.services.cab")


class CabService:
    """Change Advisory Board reviews: scheduling, voting, and closing them out."""

    def __init__(
        self,
        cab: ChangeCabRepository,
        votes: ChangeCabVoteRepository,
        changes: ChangeRequestRepository,
        notifications: ChangeNotificationService,
        *,
        publish_event: EventPublisher | None = None,
        quorum_fraction: float = 0.5,
    ) -> None:
        self._cab = cab
        self._votes = votes
        self._changes = changes
        self._notifications = notifications
        self._publish = publish_event
        self._quorum_fraction = quorum_fraction

    async def _publish_event(self, event: Any) -> None:
        if self._publish is not None:
            await self._publish(event)

    async def schedule_review(
        self,
        organization_id: UUID,
        change_id: UUID,
        *,
        scheduled_at: datetime,
        chair_id: str | None = None,
        invited: list[str],
        agenda: str | None = None,
        is_emergency_cab: bool = False,
        is_virtual: bool = False,
    ) -> ChangeCab:
        """Open a CAB review for a change awaiting one.

        Raises:
            ConflictError: If the change is not ``CAB_REVIEW``, or a
                review has already been opened for it.
        """
        stored = await self._changes.require_in_org(organization_id, change_id)
        current = change_status_of(stored.status)
        if current is not ChangeStatus.CAB_REVIEW:
            raise ConflictError(f"{stored.reference} is {current!s}; no CAB review is due.")
        if await self._cab.get_for_change(organization_id, change_id) is not None:
            raise ConflictError(f"A CAB review already exists for {stored.reference}.")

        created = await self._cab.create(
            ChangeCab(
                organization_id=organization_id,
                change_id=change_id,
                status=CabMeetingStatus.SCHEDULED,
                scheduled_at=scheduled_at,
                chair_id=chair_id,
                agenda=agenda,
                is_emergency_cab=is_emergency_cab,
                is_virtual=is_virtual,
                quorum_fraction_required=self._quorum_fraction,
                invited_count=len(invited),
            )
        )
        for member_id in invited:
            await self._notifications.send_cab_meeting_scheduled(
                member_id,
                reference=stored.reference,
                title=stored.title,
                scheduled_at=scheduled_at.isoformat(),
            )
        return created

    async def cast_vote(
        self,
        organization_id: UUID,
        cab_id: UUID,
        *,
        voter_id: str,
        vote: CabVote,
        comment: str | None = None,
        now: datetime | None = None,
    ) -> ChangeCabVote:
        """Record one board member's vote.

        Raises:
            ConflictError: If the review is not currently in progress,
                or this member has already voted.
        """
        moment = now or datetime.now(UTC)
        review = await self._cab.require_in_org(organization_id, cab_id)
        status = cab_meeting_status_of(review.status)
        if status not in (CabMeetingStatus.SCHEDULED, CabMeetingStatus.IN_PROGRESS):
            raise ConflictError(f"CAB review {cab_id} is {status!s}; voting is closed.")
        if status is CabMeetingStatus.SCHEDULED:
            review.status = CabMeetingStatus.IN_PROGRESS
            review.held_at = moment
            await self._cab.update(review)

        if await self._votes.get_for_voter(organization_id, cab_id, voter_id) is not None:
            raise ConflictError(f"{voter_id} has already voted at this review.")

        return await self._votes.create(
            ChangeCabVote(
                organization_id=organization_id,
                cab_id=cab_id,
                voter_id=voter_id,
                vote=vote,
                comment=comment,
                voted_at=moment,
            )
        )

    async def close_meeting(self, organization_id: UUID, cab_id: UUID) -> ChangeCab:
        """Tally a review's votes and resolve the change it was reviewing.

        Raises:
            ConflictError: If the review is already closed.
        """
        review = await self._cab.require_in_org(organization_id, cab_id)
        status = cab_meeting_status_of(review.status)
        if status is CabMeetingStatus.COMPLETED:
            raise ConflictError(f"CAB review {cab_id} is already closed.")

        votes = await self._votes.list_for_cab(organization_id, cab_id)
        result = tally(
            [cab_vote_of(one.vote) for one in votes],
            invited_count=review.invited_count,
            quorum_fraction=review.quorum_fraction_required,
        )
        review.status = CabMeetingStatus.COMPLETED
        review.quorum_met = result.quorum_met
        review.outcome = result.outcome
        await self._cab.update(review)

        stored = await self._changes.require_in_org(organization_id, review.change_id)
        if result.outcome is CabVote.REJECT:
            validate_transition(change_status_of(stored.status), ChangeStatus.REJECTED)
            stored.status = ChangeStatus.REJECTED
            await self._changes.update(stored)
        elif result.outcome in (CabVote.APPROVE, CabVote.CONDITIONAL):
            moment = datetime.now(UTC)
            stored.approved_at = moment
            if stored.submitted_at is not None:
                stored.approval_duration_seconds = (moment - stored.submitted_at).total_seconds()
            await self._changes.update(stored)
            await self._publish_event(
                CabApprovedEvent(
                    source_service=SOURCE_SERVICE,
                    payload={
                        "organization_id": str(organization_id),
                        "change_id": str(review.change_id),
                        "outcome": str(result.outcome),
                    },
                )
            )
        # Quorum not met, or every vote an abstention: the change stays
        # in CAB_REVIEW. Nothing was decided, so nothing here should
        # look like a decision was made.
        return review

    async def get_for_change(self, organization_id: UUID, change_id: UUID) -> ChangeCab | None:
        """The CAB review for one change, if one has been opened."""
        return await self._cab.get_for_change(organization_id, change_id)

    async def list_votes(self, organization_id: UUID, cab_id: UUID) -> list[ChangeCabVote]:
        """Every vote cast at one review."""
        return await self._votes.list_for_cab(organization_id, cab_id)


__all__ = ["CabService"]
