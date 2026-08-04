"""DependencyService: dependency edges, cycle prevention, and readiness checks.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from shared_core.exceptions.not_found import NotFoundError
from shared_core.exceptions.validation import ValidationError

from app.models.enums import DependencyCondition, DependencyType, ExecutionStatus
from app.repositories.execution import JobExecutionLogRepository, JobExecutionRepository
from app.repositories.history import JobFailureRepository
from app.repositories.job import ScheduledJobRepository
from app.repositories.retry import JobRetryPolicyRepository
from app.services.dependency import DependencyService
from app.services.execution import ExecutionService
from app.services.job import JobService

pytestmark = pytest.mark.asyncio


async def _make_failing_execution_service(
    db_session, job_service: JobService, notifications
) -> ExecutionService:
    """An :class:`ExecutionService` whose publisher raises once ``dispatch`` reaches
    ``JobCompletedEvent`` -- inside ``dispatch``'s own try/except, so the failure
    routes through ``_handle_failure`` and the execution ends ``FAILED`` rather
    than the exception escaping ``dispatch`` itself (``JobStartedEvent`` publishes
    *before* that try block, so it must not raise).
    """

    async def _raise_on_completed(event: object) -> None:
        if getattr(event, "event_name", None) == "JobCompleted":
            raise RuntimeError("synthetic failure for test")

    return ExecutionService(
        JobExecutionRepository(db_session),
        JobExecutionLogRepository(db_session),
        JobFailureRepository(db_session),
        ScheduledJobRepository(db_session),
        JobRetryPolicyRepository(db_session),
        job_service,
        notifications,
        publish_event=_raise_on_completed,
    )


class TestAddDependency:
    async def test_creates_a_dependency_edge(
        self, dependency_service: DependencyService, organization_id, make_job
    ) -> None:
        parent = await make_job("Parent")
        child = await make_job("Child")
        created = await dependency_service.add_dependency(
            organization_id, parent_job_id=parent.id, child_job_id=child.id
        )
        assert created.parent_job_id == parent.id
        assert created.child_job_id == child.id

    async def test_defaults_dependency_type_to_sequential_and_condition_to_none(
        self, dependency_service: DependencyService, organization_id, make_job
    ) -> None:
        parent = await make_job("Parent")
        child = await make_job("Child")
        created = await dependency_service.add_dependency(
            organization_id, parent_job_id=parent.id, child_job_id=child.id
        )
        assert created.dependency_type == DependencyType.SEQUENTIAL
        assert created.condition is None

    async def test_stores_a_given_dependency_type_and_condition(
        self, dependency_service: DependencyService, organization_id, make_job
    ) -> None:
        parent = await make_job("Parent")
        child = await make_job("Child")
        created = await dependency_service.add_dependency(
            organization_id,
            parent_job_id=parent.id,
            child_job_id=child.id,
            dependency_type=DependencyType.CONDITIONAL,
            condition=DependencyCondition.ON_FAILURE,
        )
        assert created.dependency_type == DependencyType.CONDITIONAL
        assert created.condition == DependencyCondition.ON_FAILURE

    async def test_raises_validation_error_for_a_self_dependency(
        self, dependency_service: DependencyService, organization_id, make_job
    ) -> None:
        job = await make_job("Solo job")
        with pytest.raises(ValidationError):
            await dependency_service.add_dependency(
                organization_id, parent_job_id=job.id, child_job_id=job.id
            )

    async def test_raises_not_found_if_the_parent_job_does_not_exist(
        self, dependency_service: DependencyService, organization_id, make_job
    ) -> None:
        child = await make_job("Child")
        with pytest.raises(NotFoundError):
            await dependency_service.add_dependency(
                organization_id, parent_job_id=uuid4(), child_job_id=child.id
            )

    async def test_raises_not_found_if_the_child_job_does_not_exist(
        self, dependency_service: DependencyService, organization_id, make_job
    ) -> None:
        parent = await make_job("Parent")
        with pytest.raises(NotFoundError):
            await dependency_service.add_dependency(
                organization_id, parent_job_id=parent.id, child_job_id=uuid4()
            )

    async def test_raises_validation_error_for_a_cycle(
        self, dependency_service: DependencyService, organization_id, make_job
    ) -> None:
        job_a = await make_job("A")
        job_b = await make_job("B")
        job_c = await make_job("C")
        await dependency_service.add_dependency(
            organization_id, parent_job_id=job_a.id, child_job_id=job_b.id
        )
        await dependency_service.add_dependency(
            organization_id, parent_job_id=job_b.id, child_job_id=job_c.id
        )
        with pytest.raises(ValidationError):
            await dependency_service.add_dependency(
                organization_id, parent_job_id=job_c.id, child_job_id=job_a.id
            )


class TestRemove:
    async def test_removes_a_dependency_edge(
        self, dependency_service: DependencyService, organization_id, make_job
    ) -> None:
        parent = await make_job("Parent")
        child = await make_job("Child")
        created = await dependency_service.add_dependency(
            organization_id, parent_job_id=parent.id, child_job_id=child.id
        )
        await dependency_service.remove(organization_id, created.id)
        found = await dependency_service.list_for_job(organization_id, child.id)
        assert found == []

    async def test_raises_not_found_for_a_missing_edge_id(
        self, dependency_service: DependencyService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await dependency_service.remove(organization_id, uuid4())


class TestListForJob:
    async def test_returns_every_edge_where_the_job_is_the_child(
        self, dependency_service: DependencyService, organization_id, make_job
    ) -> None:
        parent_one = await make_job("Parent one")
        parent_two = await make_job("Parent two")
        child = await make_job("Child")
        await dependency_service.add_dependency(
            organization_id, parent_job_id=parent_one.id, child_job_id=child.id
        )
        await dependency_service.add_dependency(
            organization_id, parent_job_id=parent_two.id, child_job_id=child.id
        )
        found = await dependency_service.list_for_job(organization_id, child.id)
        assert {one.parent_job_id for one in found} == {parent_one.id, parent_two.id}

    async def test_excludes_edges_where_the_job_is_the_parent_side(
        self, dependency_service: DependencyService, organization_id, make_job
    ) -> None:
        parent = await make_job("Parent")
        child = await make_job("Child")
        await dependency_service.add_dependency(
            organization_id, parent_job_id=parent.id, child_job_id=child.id
        )
        found = await dependency_service.list_for_job(organization_id, parent.id)
        assert found == []


class TestIsReadyToRun:
    async def test_true_when_the_job_has_no_dependencies(
        self, dependency_service: DependencyService, organization_id, make_job
    ) -> None:
        job = await make_job("Standalone")
        assert await dependency_service.is_ready_to_run(organization_id, job.id) is True

    async def test_false_when_the_parent_has_never_run(
        self, dependency_service: DependencyService, organization_id, make_job
    ) -> None:
        parent = await make_job("Parent")
        child = await make_job("Child")
        await dependency_service.add_dependency(
            organization_id, parent_job_id=parent.id, child_job_id=child.id
        )
        assert await dependency_service.is_ready_to_run(organization_id, child.id) is False

    async def test_true_once_the_default_condition_parent_completes(
        self,
        dependency_service: DependencyService,
        execution_service: ExecutionService,
        organization_id,
        make_job,
    ) -> None:
        parent = await make_job("Parent")
        child = await make_job("Child")
        await dependency_service.add_dependency(
            organization_id, parent_job_id=parent.id, child_job_id=child.id
        )
        assert await dependency_service.is_ready_to_run(organization_id, child.id) is False

        await execution_service.dispatch(organization_id, parent.id, trigger_source="manual")
        assert await dependency_service.is_ready_to_run(organization_id, child.id) is True

    async def test_on_completion_condition_is_satisfied_by_any_terminal_status(
        self,
        dependency_service: DependencyService,
        execution_service: ExecutionService,
        organization_id,
        make_job,
    ) -> None:
        parent = await make_job("Parent")
        child = await make_job("Child")
        await dependency_service.add_dependency(
            organization_id,
            parent_job_id=parent.id,
            child_job_id=child.id,
            condition=DependencyCondition.ON_COMPLETION,
        )
        await execution_service.dispatch(organization_id, parent.id, trigger_source="manual")
        assert await dependency_service.is_ready_to_run(organization_id, child.id) is True

    async def test_on_failure_condition_is_satisfied_by_a_failed_latest_execution(
        self,
        dependency_service: DependencyService,
        job_service: JobService,
        notifications,
        db_session,
        organization_id,
        make_job,
    ) -> None:
        parent = await make_job("Flaky parent")
        child = await make_job("Dependent child")
        await dependency_service.add_dependency(
            organization_id,
            parent_job_id=parent.id,
            child_job_id=child.id,
            condition=DependencyCondition.ON_FAILURE,
        )
        assert await dependency_service.is_ready_to_run(organization_id, child.id) is False

        failing_execution_service = await _make_failing_execution_service(
            db_session, job_service, notifications
        )
        execution = await failing_execution_service.dispatch(
            organization_id, parent.id, trigger_source="manual"
        )
        assert execution.status == ExecutionStatus.FAILED
        assert await dependency_service.is_ready_to_run(organization_id, child.id) is True

    async def test_on_failure_condition_is_not_satisfied_by_a_completed_parent(
        self,
        dependency_service: DependencyService,
        execution_service: ExecutionService,
        organization_id,
        make_job,
    ) -> None:
        parent = await make_job("Reliable parent")
        child = await make_job("Child")
        await dependency_service.add_dependency(
            organization_id,
            parent_job_id=parent.id,
            child_job_id=child.id,
            condition=DependencyCondition.ON_FAILURE,
        )
        await execution_service.dispatch(organization_id, parent.id, trigger_source="manual")
        assert await dependency_service.is_ready_to_run(organization_id, child.id) is False

    async def test_requires_every_dependency_edge_to_be_satisfied(
        self,
        dependency_service: DependencyService,
        execution_service: ExecutionService,
        organization_id,
        make_job,
    ) -> None:
        first_parent = await make_job("First parent")
        second_parent = await make_job("Second parent")
        child = await make_job("Child")
        await dependency_service.add_dependency(
            organization_id, parent_job_id=first_parent.id, child_job_id=child.id
        )
        await dependency_service.add_dependency(
            organization_id, parent_job_id=second_parent.id, child_job_id=child.id
        )

        await execution_service.dispatch(organization_id, first_parent.id, trigger_source="manual")
        assert await dependency_service.is_ready_to_run(organization_id, child.id) is False

        await execution_service.dispatch(organization_id, second_parent.id, trigger_source="manual")
        assert await dependency_service.is_ready_to_run(organization_id, child.id) is True
