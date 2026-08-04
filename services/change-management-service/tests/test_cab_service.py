"""CabService: scheduling, voting on, and closing a CAB review.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

import pytest
from shared_core.exceptions.conflict import ConflictError
from tests.conftest import soon

from app.models.enums import CabMeetingStatus, CabVote, ChangeStatus
from app.services.cab import CabService
from app.services.change import ChangeService

pytestmark = pytest.mark.asyncio


class TestScheduleReview:
    async def test_wrong_status_raises_conflict_error(
        self, cab_service: CabService, organization_id, make_assessed_change
    ) -> None:
        change = await make_assessed_change()  # MEDIUM risk: still PENDING_APPROVAL
        with pytest.raises(ConflictError):
            await cab_service.schedule_review(
                organization_id, change.id, scheduled_at=soon(2), invited=["member-1"]
            )

    async def test_creates_a_scheduled_review_with_the_invited_count(
        self, cab_service: CabService, organization_id, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        created = await cab_service.schedule_review(
            organization_id,
            change.id,
            scheduled_at=soon(2),
            invited=["member-1", "member-2"],
            chair_id="chair-1",
        )
        assert created.status == CabMeetingStatus.SCHEDULED
        assert created.invited_count == 2
        assert created.chair_id == "chair-1"
        assert created.quorum_fraction_required == 0.5

    async def test_raises_conflict_error_if_a_review_already_exists(
        self, cab_service: CabService, organization_id, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        await cab_service.schedule_review(
            organization_id, change.id, scheduled_at=soon(2), invited=["member-1"]
        )
        with pytest.raises(ConflictError):
            await cab_service.schedule_review(
                organization_id, change.id, scheduled_at=soon(3), invited=["member-2"]
            )


class TestCastVote:
    async def test_the_first_vote_flips_a_scheduled_review_to_in_progress(
        self, cab_service: CabService, organization_id, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        review = await cab_service.schedule_review(
            organization_id, change.id, scheduled_at=soon(2), invited=["member-1", "member-2"]
        )
        vote = await cab_service.cast_vote(
            organization_id, review.id, voter_id="member-1", vote=CabVote.APPROVE
        )
        assert vote.voter_id == "member-1"
        refreshed = await cab_service.get_for_change(organization_id, change.id)
        assert refreshed.status == CabMeetingStatus.IN_PROGRESS
        assert refreshed.held_at is not None

    async def test_a_second_distinct_voter_does_not_disturb_the_in_progress_status(
        self, cab_service: CabService, organization_id, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        review = await cab_service.schedule_review(
            organization_id, change.id, scheduled_at=soon(2), invited=["member-1", "member-2"]
        )
        await cab_service.cast_vote(
            organization_id, review.id, voter_id="member-1", vote=CabVote.APPROVE
        )
        held_at_after_first_vote = (
            await cab_service.get_for_change(organization_id, change.id)
        ).held_at
        await cab_service.cast_vote(
            organization_id, review.id, voter_id="member-2", vote=CabVote.APPROVE
        )
        refreshed = await cab_service.get_for_change(organization_id, change.id)
        assert refreshed.status == CabMeetingStatus.IN_PROGRESS
        assert refreshed.held_at == held_at_after_first_vote

    async def test_raises_conflict_error_for_a_closed_review(
        self, cab_service: CabService, organization_id, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        review = await cab_service.schedule_review(
            organization_id, change.id, scheduled_at=soon(2), invited=["member-1"]
        )
        await cab_service.cast_vote(
            organization_id, review.id, voter_id="member-1", vote=CabVote.APPROVE
        )
        await cab_service.close_meeting(organization_id, review.id)
        with pytest.raises(ConflictError):
            await cab_service.cast_vote(
                organization_id, review.id, voter_id="member-2", vote=CabVote.APPROVE
            )

    async def test_raises_conflict_error_for_a_voter_who_already_voted(
        self, cab_service: CabService, organization_id, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        review = await cab_service.schedule_review(
            organization_id, change.id, scheduled_at=soon(2), invited=["member-1", "member-2"]
        )
        await cab_service.cast_vote(
            organization_id, review.id, voter_id="member-1", vote=CabVote.APPROVE
        )
        with pytest.raises(ConflictError):
            await cab_service.cast_vote(
                organization_id, review.id, voter_id="member-1", vote=CabVote.REJECT
            )


class TestCloseMeeting:
    async def test_a_single_approval_meets_quorum_with_two_invited_and_approves_the_change(
        self,
        cab_service: CabService,
        change_service: ChangeService,
        organization_id,
        make_cab_review_change,
        publisher,
    ) -> None:
        change = await make_cab_review_change()
        # Deciding the approval chain already stamped `approved_at` (it
        # does so regardless of `cab_required`), so the meaningful check
        # here is that the CAB's own favourable outcome re-stamps it with
        # its own, later moment -- not merely that it is non-null.
        approved_at_before_cab = change.approved_at
        review = await cab_service.schedule_review(
            organization_id, change.id, scheduled_at=soon(2), invited=["member-1", "member-2"]
        )
        await cab_service.cast_vote(
            organization_id, review.id, voter_id="member-1", vote=CabVote.APPROVE
        )
        closed = await cab_service.close_meeting(organization_id, review.id)
        assert closed.status == CabMeetingStatus.COMPLETED
        assert closed.quorum_met is True
        assert closed.outcome == CabVote.APPROVE
        updated = await change_service.get(organization_id, change.id)
        assert updated.status == ChangeStatus.CAB_REVIEW
        assert updated.approved_at is not None
        assert updated.approved_at > approved_at_before_cab
        assert "CABApproved" in publisher.names

    async def test_a_single_rejection_sinks_the_review_regardless_of_other_approvals(
        self,
        cab_service: CabService,
        change_service: ChangeService,
        organization_id,
        make_cab_review_change,
        publisher,
    ) -> None:
        change = await make_cab_review_change()
        review = await cab_service.schedule_review(
            organization_id,
            change.id,
            scheduled_at=soon(2),
            invited=["member-1", "member-2", "member-3", "member-4"],
        )
        await cab_service.cast_vote(
            organization_id, review.id, voter_id="member-1", vote=CabVote.APPROVE
        )
        await cab_service.cast_vote(
            organization_id, review.id, voter_id="member-2", vote=CabVote.APPROVE
        )
        await cab_service.cast_vote(
            organization_id, review.id, voter_id="member-3", vote=CabVote.REJECT
        )
        closed = await cab_service.close_meeting(organization_id, review.id)
        assert closed.outcome == CabVote.REJECT
        updated = await change_service.get(organization_id, change.id)
        assert updated.status == ChangeStatus.REJECTED
        assert "CABApproved" not in publisher.names

    async def test_a_conditional_vote_makes_the_outcome_conditional(
        self,
        cab_service: CabService,
        change_service: ChangeService,
        organization_id,
        make_cab_review_change,
        publisher,
    ) -> None:
        change = await make_cab_review_change()
        approved_at_before_cab = change.approved_at
        review = await cab_service.schedule_review(
            organization_id, change.id, scheduled_at=soon(2), invited=["member-1", "member-2"]
        )
        await cab_service.cast_vote(
            organization_id, review.id, voter_id="member-1", vote=CabVote.APPROVE
        )
        await cab_service.cast_vote(
            organization_id, review.id, voter_id="member-2", vote=CabVote.CONDITIONAL
        )
        closed = await cab_service.close_meeting(organization_id, review.id)
        assert closed.outcome == CabVote.CONDITIONAL
        updated = await change_service.get(organization_id, change.id)
        assert updated.status == ChangeStatus.CAB_REVIEW
        assert updated.approved_at is not None
        assert updated.approved_at > approved_at_before_cab
        assert "CABApproved" in publisher.names

    async def test_quorum_not_met_leaves_the_change_untouched(
        self,
        cab_service: CabService,
        change_service: ChangeService,
        organization_id,
        make_cab_review_change,
        publisher,
    ) -> None:
        change = await make_cab_review_change()
        # `approved_at` is already set here -- deciding the approval chain
        # sets it regardless of `cab_required`, per `ApprovalService.decide`.
        # A quorum failure at CAB must leave that value alone rather than
        # clearing it or stamping a fresh one.
        approved_at_before_cab = change.approved_at
        review = await cab_service.schedule_review(
            organization_id,
            change.id,
            scheduled_at=soon(2),
            invited=["member-1", "member-2", "member-3", "member-4"],
        )
        publisher.events.clear()
        await cab_service.cast_vote(
            organization_id, review.id, voter_id="member-1", vote=CabVote.APPROVE
        )
        closed = await cab_service.close_meeting(organization_id, review.id)
        assert closed.status == CabMeetingStatus.COMPLETED
        assert closed.quorum_met is False
        assert closed.outcome is None
        updated = await change_service.get(organization_id, change.id)
        assert updated.status == ChangeStatus.CAB_REVIEW
        assert updated.approved_at == approved_at_before_cab
        assert publisher.events == []

    async def test_all_abstentions_meet_quorum_but_decide_nothing(
        self,
        cab_service: CabService,
        change_service: ChangeService,
        organization_id,
        make_cab_review_change,
    ) -> None:
        change = await make_cab_review_change()
        approved_at_before_cab = change.approved_at
        review = await cab_service.schedule_review(
            organization_id, change.id, scheduled_at=soon(2), invited=["member-1", "member-2"]
        )
        await cab_service.cast_vote(
            organization_id, review.id, voter_id="member-1", vote=CabVote.ABSTAIN
        )
        closed = await cab_service.close_meeting(organization_id, review.id)
        assert closed.quorum_met is True
        assert closed.outcome is None
        updated = await change_service.get(organization_id, change.id)
        assert updated.status == ChangeStatus.CAB_REVIEW
        assert updated.approved_at == approved_at_before_cab

    async def test_raises_conflict_error_when_already_closed(
        self, cab_service: CabService, organization_id, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        review = await cab_service.schedule_review(
            organization_id, change.id, scheduled_at=soon(2), invited=["member-1"]
        )
        await cab_service.cast_vote(
            organization_id, review.id, voter_id="member-1", vote=CabVote.APPROVE
        )
        await cab_service.close_meeting(organization_id, review.id)
        with pytest.raises(ConflictError):
            await cab_service.close_meeting(organization_id, review.id)


class TestGetForChange:
    async def test_returns_none_when_no_review_has_been_opened(
        self, cab_service: CabService, organization_id, make_assessed_change
    ) -> None:
        change = await make_assessed_change()
        assert await cab_service.get_for_change(organization_id, change.id) is None

    async def test_returns_the_review_once_one_has_been_scheduled(
        self, cab_service: CabService, organization_id, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        created = await cab_service.schedule_review(
            organization_id, change.id, scheduled_at=soon(2), invited=["member-1"]
        )
        found = await cab_service.get_for_change(organization_id, change.id)
        assert found is not None
        assert found.id == created.id


class TestListVotes:
    async def test_lists_every_vote_cast_at_the_review(
        self, cab_service: CabService, organization_id, make_cab_review_change
    ) -> None:
        change = await make_cab_review_change()
        review = await cab_service.schedule_review(
            organization_id, change.id, scheduled_at=soon(2), invited=["member-1", "member-2"]
        )
        await cab_service.cast_vote(
            organization_id, review.id, voter_id="member-1", vote=CabVote.APPROVE
        )
        await cab_service.cast_vote(
            organization_id, review.id, voter_id="member-2", vote=CabVote.CONDITIONAL
        )
        votes = await cab_service.list_votes(organization_id, review.id)
        assert {one.voter_id for one in votes} == {"member-1", "member-2"}
