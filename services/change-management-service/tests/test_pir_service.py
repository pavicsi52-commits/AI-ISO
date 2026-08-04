"""PirService: post-implementation review authoring, action items, and approval.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.models.enums import ChangeTaskStatus, PirStatus
from app.services.pir import PirService

pytestmark = pytest.mark.asyncio


class TestStart:
    async def test_raises_validation_error_if_the_change_has_not_finished(
        self, pir_service: PirService, make_ready_change, organization_id
    ) -> None:
        change = await make_ready_change()
        with pytest.raises(ValidationError):
            await pir_service.start(organization_id, change.id)

    async def test_starts_a_review_for_a_completed_change(
        self, pir_service: PirService, make_completed_change, organization_id
    ) -> None:
        change = await make_completed_change()
        review = await pir_service.start(organization_id, change.id, owner_id="owner-1")
        assert review.status == PirStatus.DRAFT
        assert review.owner_id == "owner-1"

    async def test_starts_a_review_for_a_rolled_back_change(
        self,
        pir_service: PirService,
        rollback_service,
        make_in_progress_change,
        organization_id,
    ) -> None:
        change = await make_in_progress_change()
        planned = await rollback_service.plan(
            organization_id, change.id, plan="Restore", triggered_reason="Broke prod"
        )
        await rollback_service.approve(organization_id, planned.id, approved_by="manager-1")
        await rollback_service.start(organization_id, planned.id)
        review = await pir_service.start(organization_id, change.id)
        assert review.status == PirStatus.DRAFT

    async def test_starts_a_review_for_a_closed_change(
        self, pir_service: PirService, change_service, make_completed_change, organization_id
    ) -> None:
        change = await make_completed_change()
        closed = await change_service.close(organization_id, change.id)
        review = await pir_service.start(organization_id, closed.id)
        assert review.status == PirStatus.DRAFT

    async def test_raises_conflict_error_if_a_review_already_exists(
        self, pir_service: PirService, make_completed_change, organization_id
    ) -> None:
        change = await make_completed_change()
        await pir_service.start(organization_id, change.id)
        with pytest.raises(ConflictError):
            await pir_service.start(organization_id, change.id)


class TestUpdateContent:
    async def test_updates_content_fields(
        self, pir_service: PirService, make_completed_change, organization_id
    ) -> None:
        change = await make_completed_change()
        review = await pir_service.start(organization_id, change.id)
        updated = await pir_service.update_content(
            organization_id,
            review.id,
            implementation_summary="Went smoothly.",
            lessons_learned="Automate the manual step next time.",
        )
        assert updated.implementation_summary == "Went smoothly."
        assert updated.lessons_learned == "Automate the manual step next time."

    async def test_raises_conflict_error_once_approved(
        self, pir_service: PirService, make_completed_change, organization_id
    ) -> None:
        change = await make_completed_change()
        review = await pir_service.start(organization_id, change.id)
        await pir_service.transition(organization_id, review.id, target=PirStatus.IN_REVIEW)
        await pir_service.transition(organization_id, review.id, target=PirStatus.APPROVED)
        with pytest.raises(ConflictError):
            await pir_service.update_content(
                organization_id, review.id, implementation_summary="Too late."
            )


class TestActionItems:
    async def test_add_action_item_defaults_to_pending(
        self, pir_service: PirService, make_completed_change, organization_id
    ) -> None:
        change = await make_completed_change()
        review = await pir_service.start(organization_id, change.id)
        item = await pir_service.add_action_item(
            organization_id, review.id, title="Automate the step"
        )
        assert item.status == ChangeTaskStatus.PENDING
        assert item.title == "Automate the step"

    async def test_add_action_item_raises_not_found_for_a_missing_review(
        self, pir_service: PirService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await pir_service.add_action_item(organization_id, uuid4(), title="x")

    async def test_complete_action_item_sets_status_and_timestamp(
        self, pir_service: PirService, make_completed_change, organization_id
    ) -> None:
        change = await make_completed_change()
        review = await pir_service.start(organization_id, change.id)
        item = await pir_service.add_action_item(organization_id, review.id, title="Follow up")
        updated = await pir_service.complete_action_item(organization_id, item.id)
        assert updated.status == ChangeTaskStatus.COMPLETED
        assert updated.completed_at is not None

    async def test_complete_action_item_raises_not_found_for_a_missing_item(
        self, pir_service: PirService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await pir_service.complete_action_item(organization_id, uuid4())

    async def test_action_items_lists_every_item_for_a_review(
        self, pir_service: PirService, make_completed_change, organization_id
    ) -> None:
        change = await make_completed_change()
        review = await pir_service.start(organization_id, change.id)
        await pir_service.add_action_item(organization_id, review.id, title="One")
        await pir_service.add_action_item(organization_id, review.id, title="Two")
        found = await pir_service.action_items(organization_id, review.id)
        assert len(found) == 2

    async def test_action_items_raises_not_found_for_a_missing_review(
        self, pir_service: PirService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await pir_service.action_items(organization_id, uuid4())

    async def test_open_action_items_for_owner_excludes_completed(
        self, pir_service: PirService, make_completed_change, organization_id
    ) -> None:
        change = await make_completed_change()
        review = await pir_service.start(organization_id, change.id)
        open_item = await pir_service.add_action_item(
            organization_id, review.id, title="Still open", owner_id="owner-9"
        )
        done_item = await pir_service.add_action_item(
            organization_id, review.id, title="Already done", owner_id="owner-9"
        )
        await pir_service.complete_action_item(organization_id, done_item.id)
        found = await pir_service.open_action_items_for(organization_id, "owner-9")
        ids = {one.id for one in found}
        assert open_item.id in ids
        assert done_item.id not in ids


class TestTransition:
    async def test_draft_to_in_review_succeeds(
        self, pir_service: PirService, make_completed_change, organization_id
    ) -> None:
        change = await make_completed_change()
        review = await pir_service.start(organization_id, change.id)
        updated = await pir_service.transition(
            organization_id, review.id, target=PirStatus.IN_REVIEW
        )
        assert updated.status == PirStatus.IN_REVIEW

    async def test_illegal_transition_raises_validation_error(
        self, pir_service: PirService, make_completed_change, organization_id
    ) -> None:
        change = await make_completed_change()
        review = await pir_service.start(organization_id, change.id)
        with pytest.raises(ValidationError):
            await pir_service.transition(organization_id, review.id, target=PirStatus.APPROVED)

    async def test_in_review_can_go_back_to_draft(
        self, pir_service: PirService, make_completed_change, organization_id
    ) -> None:
        change = await make_completed_change()
        review = await pir_service.start(organization_id, change.id)
        await pir_service.transition(organization_id, review.id, target=PirStatus.IN_REVIEW)
        sent_back = await pir_service.transition(organization_id, review.id, target=PirStatus.DRAFT)
        assert sent_back.status == PirStatus.DRAFT

    async def test_approval_is_blocked_by_an_unowned_action_item(
        self, pir_service: PirService, make_completed_change, organization_id
    ) -> None:
        change = await make_completed_change()
        review = await pir_service.start(organization_id, change.id)
        await pir_service.add_action_item(organization_id, review.id, title="Needs an owner")
        await pir_service.transition(organization_id, review.id, target=PirStatus.IN_REVIEW)
        with pytest.raises(ValidationError):
            await pir_service.transition(organization_id, review.id, target=PirStatus.APPROVED)

    async def test_a_skipped_action_item_does_not_need_an_owner_to_approve(
        self,
        pir_service: PirService,
        pir_action_items_repo,
        make_completed_change,
        organization_id,
    ) -> None:
        change = await make_completed_change()
        review = await pir_service.start(organization_id, change.id)
        item = await pir_service.add_action_item(organization_id, review.id, title="Not needed")
        item.status = ChangeTaskStatus.SKIPPED
        await pir_action_items_repo.update(item)
        await pir_service.transition(organization_id, review.id, target=PirStatus.IN_REVIEW)
        approved = await pir_service.transition(
            organization_id, review.id, target=PirStatus.APPROVED, actor_id="cab-1"
        )
        assert approved.status == PirStatus.APPROVED

    async def test_approving_sets_approver_and_publishes_completed(
        self, pir_service: PirService, make_completed_change, organization_id, publisher
    ) -> None:
        change = await make_completed_change()
        review = await pir_service.start(organization_id, change.id)
        await pir_service.add_action_item(
            organization_id, review.id, title="Owned", owner_id="owner-1"
        )
        await pir_service.transition(organization_id, review.id, target=PirStatus.IN_REVIEW)
        publisher.events.clear()
        approved = await pir_service.transition(
            organization_id, review.id, target=PirStatus.APPROVED, actor_id="cab-1"
        )
        assert approved.approved_by == "cab-1"
        assert approved.approved_at is not None
        assert "PIRCompleted" in publisher.names

    async def test_approved_is_a_dead_end(
        self, pir_service: PirService, make_completed_change, organization_id
    ) -> None:
        change = await make_completed_change()
        review = await pir_service.start(organization_id, change.id)
        await pir_service.transition(organization_id, review.id, target=PirStatus.IN_REVIEW)
        await pir_service.transition(organization_id, review.id, target=PirStatus.APPROVED)
        with pytest.raises(ValidationError):
            await pir_service.transition(organization_id, review.id, target=PirStatus.DRAFT)


class TestGetAndGetForChange:
    async def test_get_raises_not_found_for_a_missing_review(
        self, pir_service: PirService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await pir_service.get(organization_id, uuid4())

    async def test_get_for_change_returns_none_if_no_review_exists(
        self, pir_service: PirService, make_completed_change, organization_id
    ) -> None:
        change = await make_completed_change()
        found = await pir_service.get_for_change(organization_id, change.id)
        assert found is None

    async def test_get_for_change_returns_the_review(
        self, pir_service: PirService, make_completed_change, organization_id
    ) -> None:
        change = await make_completed_change()
        created = await pir_service.start(organization_id, change.id)
        found = await pir_service.get_for_change(organization_id, change.id)
        assert found is not None
        assert found.id == created.id
