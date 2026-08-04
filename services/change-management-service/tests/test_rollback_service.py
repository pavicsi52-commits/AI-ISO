"""RollbackService: planning, approval, execution, and failure of a rollback.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.validation import ValidationError

from app.models.enums import ChangeStatus, RollbackStatus
from app.services.rollback import RollbackService

pytestmark = pytest.mark.asyncio


async def _move_to_validation(implementation_service, change, organization_id) -> None:
    task = await implementation_service.add_task(organization_id, change.id, title="Step")
    await implementation_service.complete_task(organization_id, task.id)
    await implementation_service.move_to_validation(organization_id, change.id)


class TestPlan:
    async def test_plans_a_rollback_for_an_in_progress_change(
        self, rollback_service: RollbackService, make_in_progress_change, organization_id
    ) -> None:
        change = await make_in_progress_change()
        created = await rollback_service.plan(
            organization_id,
            change.id,
            plan="Restore from snapshot",
            triggered_reason="Health checks failing",
        )
        assert created.status == RollbackStatus.PLANNED
        assert created.change_id == change.id

    async def test_plans_a_rollback_for_a_change_in_validation(
        self,
        rollback_service: RollbackService,
        implementation_service,
        make_in_progress_change,
        organization_id,
    ) -> None:
        change = await make_in_progress_change()
        await _move_to_validation(implementation_service, change, organization_id)
        created = await rollback_service.plan(
            organization_id, change.id, plan="Revert config", triggered_reason="Failed validation"
        )
        assert created.status == RollbackStatus.PLANNED

    async def test_raises_conflict_error_if_the_change_is_not_rollback_eligible(
        self, rollback_service: RollbackService, make_ready_change, organization_id
    ) -> None:
        change = await make_ready_change()
        with pytest.raises(ConflictError):
            await rollback_service.plan(
                organization_id, change.id, plan="Undo", triggered_reason="Too early"
            )


class TestApprove:
    async def test_approve_sets_approver_and_timestamp(
        self, rollback_service: RollbackService, make_in_progress_change, organization_id
    ) -> None:
        change = await make_in_progress_change()
        planned = await rollback_service.plan(
            organization_id, change.id, plan="Restore", triggered_reason="Broke prod"
        )
        approved = await rollback_service.approve(
            organization_id, planned.id, approved_by="manager-1"
        )
        assert approved.approved_by == "manager-1"
        assert approved.approved_at is not None

    async def test_raises_conflict_error_if_not_currently_planned(
        self, rollback_service: RollbackService, make_in_progress_change, organization_id
    ) -> None:
        change = await make_in_progress_change()
        planned = await rollback_service.plan(
            organization_id, change.id, plan="Restore", triggered_reason="Broke prod"
        )
        await rollback_service.approve(organization_id, planned.id, approved_by="manager-1")
        await rollback_service.start(organization_id, planned.id)
        with pytest.raises(ConflictError):
            await rollback_service.approve(organization_id, planned.id, approved_by="manager-2")


class TestStart:
    async def test_raises_conflict_error_if_not_yet_approved(
        self, rollback_service: RollbackService, make_in_progress_change, organization_id
    ) -> None:
        change = await make_in_progress_change()
        planned = await rollback_service.plan(
            organization_id, change.id, plan="Restore", triggered_reason="Broke prod"
        )
        with pytest.raises(ConflictError):
            await rollback_service.start(organization_id, planned.id)

    async def test_starting_moves_the_change_to_rolled_back_immediately(
        self,
        rollback_service: RollbackService,
        make_in_progress_change,
        change_service,
        organization_id,
        publisher,
    ) -> None:
        change = await make_in_progress_change()
        planned = await rollback_service.plan(
            organization_id, change.id, plan="Restore", triggered_reason="Broke prod"
        )
        await rollback_service.approve(organization_id, planned.id, approved_by="manager-1")
        started = await rollback_service.start(organization_id, planned.id)
        updated_change = await change_service.get(organization_id, change.id)
        assert started.status == RollbackStatus.IN_PROGRESS
        assert started.started_at is not None
        assert updated_change.status == ChangeStatus.ROLLED_BACK
        assert updated_change.actual_end_at is not None
        assert updated_change.implementation_duration_seconds is not None
        assert "RollbackStarted" in publisher.names

    async def test_raises_validation_error_if_the_change_moved_out_of_eligibility(
        self,
        rollback_service: RollbackService,
        implementation_service,
        make_in_progress_change,
        organization_id,
    ) -> None:
        change = await make_in_progress_change()
        planned = await rollback_service.plan(
            organization_id, change.id, plan="Restore", triggered_reason="Broke prod"
        )
        await rollback_service.approve(organization_id, planned.id, approved_by="manager-1")
        await _move_to_validation(implementation_service, change, organization_id)
        await implementation_service.complete(organization_id, change.id)
        with pytest.raises(ValidationError):
            await rollback_service.start(organization_id, planned.id)


class TestComplete:
    async def test_raises_conflict_error_if_not_currently_in_progress(
        self, rollback_service: RollbackService, make_in_progress_change, organization_id
    ) -> None:
        change = await make_in_progress_change()
        planned = await rollback_service.plan(
            organization_id, change.id, plan="Restore", triggered_reason="Broke prod"
        )
        with pytest.raises(ConflictError):
            await rollback_service.complete(organization_id, planned.id)

    async def test_completing_records_a_validation_summary_and_publishes_completed(
        self,
        rollback_service: RollbackService,
        make_in_progress_change,
        organization_id,
        publisher,
    ) -> None:
        change = await make_in_progress_change()
        planned = await rollback_service.plan(
            organization_id, change.id, plan="Restore", triggered_reason="Broke prod"
        )
        await rollback_service.approve(organization_id, planned.id, approved_by="manager-1")
        await rollback_service.start(organization_id, planned.id)
        publisher.events.clear()
        completed = await rollback_service.complete(
            organization_id, planned.id, validation_summary="Rollback verified healthy."
        )
        assert completed.status == RollbackStatus.COMPLETED
        assert completed.completed_at is not None
        assert completed.validation_summary == "Rollback verified healthy."
        assert "RollbackCompleted" in publisher.names


class TestFail:
    async def test_fail_marks_the_rollback_failed_but_leaves_the_change_rolled_back(
        self,
        rollback_service: RollbackService,
        make_in_progress_change,
        change_service,
        organization_id,
    ) -> None:
        change = await make_in_progress_change()
        planned = await rollback_service.plan(
            organization_id, change.id, plan="Restore", triggered_reason="Broke prod"
        )
        await rollback_service.approve(organization_id, planned.id, approved_by="manager-1")
        await rollback_service.start(organization_id, planned.id)
        failed = await rollback_service.fail(organization_id, planned.id, reason="Snapshot corrupt")
        updated_change = await change_service.get(organization_id, change.id)
        assert failed.status == RollbackStatus.FAILED
        assert failed.validation_summary == "Snapshot corrupt"
        assert updated_change.status == ChangeStatus.ROLLED_BACK


class TestListForChange:
    async def test_lists_every_rollback_attempt_for_a_change(
        self, rollback_service: RollbackService, make_in_progress_change, organization_id
    ) -> None:
        change = await make_in_progress_change()
        await rollback_service.plan(
            organization_id, change.id, plan="First attempt", triggered_reason="Reason one"
        )
        await rollback_service.plan(
            organization_id, change.id, plan="Second attempt", triggered_reason="Reason two"
        )
        found = await rollback_service.list_for_change(organization_id, change.id)
        assert len(found) == 2
