"""ImplementationService: tasks, runs, and validation gates.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.models.enums import (
    ChangeStatus,
    ChangeTaskStatus,
    ImplementationStatus,
    ValidationKind,
    ValidationStatus,
)
from app.services.implementation import ImplementationService

pytestmark = pytest.mark.asyncio


class TestAddAndListTasks:
    async def test_add_task_auto_increments_sequence(
        self, implementation_service: ImplementationService, make_ready_change, organization_id
    ) -> None:
        change = await make_ready_change()
        first = await implementation_service.add_task(organization_id, change.id, title="Step one")
        second = await implementation_service.add_task(organization_id, change.id, title="Step two")
        assert first.sequence == 0
        assert second.sequence == 1

    async def test_add_task_honors_an_explicit_sequence(
        self, implementation_service: ImplementationService, make_ready_change, organization_id
    ) -> None:
        change = await make_ready_change()
        await implementation_service.add_task(
            organization_id, change.id, title="Runs second", sequence=5
        )
        await implementation_service.add_task(
            organization_id, change.id, title="Runs first", sequence=1
        )
        tasks = await implementation_service.list_tasks(organization_id, change.id)
        assert [one.title for one in tasks] == ["Runs first", "Runs second"]

    async def test_list_tasks_is_empty_for_a_change_with_none(
        self, implementation_service: ImplementationService, make_ready_change, organization_id
    ) -> None:
        change = await make_ready_change()
        tasks = await implementation_service.list_tasks(organization_id, change.id)
        assert tasks == []


class TestCompleteAndFailTask:
    async def test_complete_task_sets_status_and_timestamp(
        self, implementation_service: ImplementationService, make_ready_change, organization_id
    ) -> None:
        change = await make_ready_change()
        task = await implementation_service.add_task(organization_id, change.id, title="Step")
        updated = await implementation_service.complete_task(organization_id, task.id)
        assert updated.status == ChangeTaskStatus.COMPLETED
        assert updated.completed_at is not None

    async def test_complete_task_records_evidence(
        self, implementation_service: ImplementationService, make_ready_change, organization_id
    ) -> None:
        change = await make_ready_change()
        task = await implementation_service.add_task(organization_id, change.id, title="Step")
        updated = await implementation_service.complete_task(
            organization_id, task.id, evidence={"log": "ok"}
        )
        assert updated.evidence == {"log": "ok"}

    async def test_complete_task_raises_not_found_for_a_missing_task(
        self, implementation_service: ImplementationService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await implementation_service.complete_task(organization_id, uuid4())

    async def test_fail_task_sets_status_failed(
        self, implementation_service: ImplementationService, make_ready_change, organization_id
    ) -> None:
        change = await make_ready_change()
        task = await implementation_service.add_task(organization_id, change.id, title="Step")
        updated = await implementation_service.fail_task(organization_id, task.id)
        assert updated.status == ChangeTaskStatus.FAILED

    async def test_fail_task_raises_not_found_for_a_missing_task(
        self, implementation_service: ImplementationService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await implementation_service.fail_task(organization_id, uuid4())


class TestStart:
    async def test_start_moves_a_ready_change_to_in_progress(
        self,
        implementation_service: ImplementationService,
        make_ready_change,
        change_service,
        organization_id,
        publisher,
    ) -> None:
        change = await make_ready_change()
        run = await implementation_service.start(organization_id, change.id)
        updated = await change_service.get(organization_id, change.id)
        assert updated.status == ChangeStatus.IN_PROGRESS
        assert updated.actual_start_at is not None
        assert run.change_id == change.id
        assert "ImplementationStarted" in publisher.names

    async def test_start_raises_validation_error_if_the_change_is_not_ready(
        self, implementation_service: ImplementationService, make_change, organization_id
    ) -> None:
        change = await make_change()
        with pytest.raises(ValidationError):
            await implementation_service.start(organization_id, change.id)


class TestRecordValidation:
    async def test_records_a_passing_validation(
        self,
        implementation_service: ImplementationService,
        make_in_progress_change,
        organization_id,
    ) -> None:
        change = await make_in_progress_change()
        created = await implementation_service.record_validation(
            organization_id,
            change.id,
            kind=ValidationKind.PRE_CHANGE,
            status=ValidationStatus.PASSED,
        )
        assert created.status == ValidationStatus.PASSED
        assert created.is_gate is False

    async def test_records_a_failing_gate_without_raising(
        self,
        implementation_service: ImplementationService,
        make_in_progress_change,
        organization_id,
    ) -> None:
        change = await make_in_progress_change(technical_owner_id="tech-1")
        created = await implementation_service.record_validation(
            organization_id,
            change.id,
            kind=ValidationKind.POST_CHANGE,
            status=ValidationStatus.FAILED,
            is_gate=True,
        )
        assert created.status == ValidationStatus.FAILED
        assert created.is_gate is True

    async def test_list_validations_returns_every_run_for_the_change(
        self,
        implementation_service: ImplementationService,
        make_in_progress_change,
        organization_id,
    ) -> None:
        change = await make_in_progress_change()
        await implementation_service.record_validation(
            organization_id,
            change.id,
            kind=ValidationKind.PRE_CHANGE,
            status=ValidationStatus.PASSED,
        )
        await implementation_service.record_validation(
            organization_id, change.id, kind=ValidationKind.HEALTH, status=ValidationStatus.PASSED
        )
        found = await implementation_service.list_validations(organization_id, change.id)
        assert len(found) == 2


class TestMoveToValidation:
    async def test_raises_conflict_error_if_a_task_is_still_pending(
        self,
        implementation_service: ImplementationService,
        make_in_progress_change,
        organization_id,
    ) -> None:
        change = await make_in_progress_change()
        await implementation_service.add_task(organization_id, change.id, title="Unfinished")
        with pytest.raises(ConflictError):
            await implementation_service.move_to_validation(organization_id, change.id)

    async def test_succeeds_once_every_task_is_finished(
        self,
        implementation_service: ImplementationService,
        make_in_progress_change,
        change_service,
        organization_id,
    ) -> None:
        change = await make_in_progress_change()
        task = await implementation_service.add_task(organization_id, change.id, title="Step")
        await implementation_service.complete_task(organization_id, task.id)
        run = await implementation_service.move_to_validation(organization_id, change.id)
        updated = await change_service.get(organization_id, change.id)
        assert updated.status == ChangeStatus.VALIDATION
        assert run.progress_percent == 100

    async def test_a_failed_task_does_not_block_moving_to_validation(
        self,
        implementation_service: ImplementationService,
        make_in_progress_change,
        organization_id,
    ) -> None:
        change = await make_in_progress_change()
        task = await implementation_service.add_task(organization_id, change.id, title="Optional")
        await implementation_service.fail_task(organization_id, task.id)
        await implementation_service.move_to_validation(organization_id, change.id)

    async def test_raises_not_found_if_no_implementation_run_exists(
        self,
        implementation_service: ImplementationService,
        make_ready_change,
        change_service,
        organization_id,
    ) -> None:
        change = await make_ready_change()
        await change_service.transition(organization_id, change.id, target=ChangeStatus.IN_PROGRESS)
        with pytest.raises(NotFoundError):
            await implementation_service.move_to_validation(organization_id, change.id)


class TestComplete:
    async def test_raises_conflict_error_if_a_gate_validation_failed(
        self,
        implementation_service: ImplementationService,
        make_in_progress_change,
        organization_id,
    ) -> None:
        change = await make_in_progress_change()
        task = await implementation_service.add_task(organization_id, change.id, title="Step")
        await implementation_service.complete_task(organization_id, task.id)
        await implementation_service.move_to_validation(organization_id, change.id)
        await implementation_service.record_validation(
            organization_id,
            change.id,
            kind=ValidationKind.POST_CHANGE,
            status=ValidationStatus.FAILED,
            is_gate=True,
        )
        with pytest.raises(ConflictError):
            await implementation_service.complete(organization_id, change.id)

    async def test_a_failed_non_gate_validation_does_not_block_completion(
        self,
        implementation_service: ImplementationService,
        make_in_progress_change,
        organization_id,
    ) -> None:
        change = await make_in_progress_change()
        task = await implementation_service.add_task(organization_id, change.id, title="Step")
        await implementation_service.complete_task(organization_id, task.id)
        await implementation_service.move_to_validation(organization_id, change.id)
        await implementation_service.record_validation(
            organization_id,
            change.id,
            kind=ValidationKind.POST_CHANGE,
            status=ValidationStatus.FAILED,
            is_gate=False,
        )
        run = await implementation_service.complete(organization_id, change.id)
        assert run.status == ImplementationStatus.COMPLETED

    async def test_completing_sets_durations_and_publishes_completed_event(
        self,
        implementation_service: ImplementationService,
        make_in_progress_change,
        change_service,
        organization_id,
        publisher,
    ) -> None:
        change = await make_in_progress_change()
        task = await implementation_service.add_task(organization_id, change.id, title="Step")
        await implementation_service.complete_task(organization_id, task.id)
        await implementation_service.move_to_validation(organization_id, change.id)
        publisher.events.clear()
        await implementation_service.complete(organization_id, change.id)
        updated = await change_service.get(organization_id, change.id)
        assert updated.status == ChangeStatus.COMPLETED
        assert updated.completed_at is not None
        assert updated.actual_end_at is not None
        assert updated.implementation_duration_seconds is not None
        assert "ImplementationCompleted" in publisher.names
