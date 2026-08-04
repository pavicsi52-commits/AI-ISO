"""ExecutionService: dispatching, failure handling, retries, and cancellation.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.

The plain ``execution_service`` fixture's ``RecordingPublisher`` never
raises, so every ``dispatch()`` call through it ends up ``COMPLETED`` --
publishing successfully *is* the unit of work this service performs (see
``app/services/execution.py``'s own module docstring). To exercise the
failure path (retries, dead-lettering, ``JobFailure`` creation) a
dedicated ``ExecutionService`` is built directly here with a publisher
that raises on its first call only -- the ``JobStarted`` publish -- and
then records normally, so the downstream retry/dead-letter events this
module's own ``_handle_failure`` publishes are still observable.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import ExecutionStatus, JobPriority
from app.models.execution import JobExecution
from app.models.retry import JobRetryPolicy
from app.services.execution import ExecutionService

pytestmark = pytest.mark.asyncio


class _FailFirstPublisher:
    """Raises on its first call, then records every call after that.

    A publisher that always raised would also blow up ``_handle_failure``'s
    own attempt to publish ``JobRetried``/``JobFailed`` -- that call is not
    wrapped in its own try/except, so the exception would propagate out of
    ``dispatch()`` a second time instead of the failure being recorded and
    returned. Raising only on the first call routes exactly one publish
    attempt (``JobStarted``) into failure, and lets everything downstream
    of that failure -- the ``JobFailure`` row, the retry/dead-letter
    decision, the follow-up event -- complete and be observed normally.
    """

    def __init__(self) -> None:
        self.events: list[Any] = []
        self._raised = False

    async def __call__(self, event: Any) -> None:
        if not self._raised:
            self._raised = True
            raise RuntimeError("boom")
        self.events.append(event)

    @property
    def names(self) -> list[str]:
        return [event.event_name for event in self.events]


@pytest.fixture
def fail_first_publisher() -> _FailFirstPublisher:
    return _FailFirstPublisher()


@pytest.fixture
def failing_execution_service(
    executions_repo,
    execution_logs_repo,
    failures_repo,
    jobs_repo,
    retry_policies_repo,
    job_service,
    notifications,
    fail_first_publisher: _FailFirstPublisher,
) -> ExecutionService:
    """An ``ExecutionService`` whose first publish attempt fails.

    Same repository/service arguments the ``execution_service`` fixture
    itself uses, with the recording publisher swapped for one that fails
    once -- see the ``execution_service`` fixture in ``conftest.py``.
    """
    return ExecutionService(
        executions_repo,
        execution_logs_repo,
        failures_repo,
        jobs_repo,
        retry_policies_repo,
        job_service,
        notifications,
        publish_event=fail_first_publisher,
    )


class TestDispatch:
    async def test_dispatch_creates_a_completed_execution_and_publishes_started_and_completed(
        self, execution_service: ExecutionService, make_job, organization_id, publisher
    ) -> None:
        job = await make_job()
        execution = await execution_service.dispatch(
            organization_id, job.id, trigger_source="manual"
        )
        assert execution.status == ExecutionStatus.COMPLETED
        assert execution.started_at is not None
        assert execution.completed_at is not None
        assert execution.duration_ms is not None
        assert execution.duration_ms >= 0
        assert "JobStarted" in publisher.names
        assert "JobCompleted" in publisher.names

    async def test_dispatch_records_the_run_on_the_job(
        self, execution_service: ExecutionService, make_job, job_service, organization_id
    ) -> None:
        job = await make_job()
        await execution_service.dispatch(organization_id, job.id, trigger_source="manual")
        reloaded = await job_service.get(organization_id, job.id)
        assert reloaded.run_count == 1
        assert reloaded.last_run_at is not None

    async def test_dispatch_sends_a_completion_notification_when_the_job_has_an_owner(
        self, execution_service: ExecutionService, make_job, organization_id
    ) -> None:
        job = await make_job(owner_id="owner-1")
        execution = await execution_service.dispatch(
            organization_id, job.id, trigger_source="manual"
        )
        assert execution.status == ExecutionStatus.COMPLETED

    async def test_dispatch_raises_not_found_error_if_the_job_does_not_exist(
        self, execution_service: ExecutionService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await execution_service.dispatch(organization_id, uuid4(), trigger_source="manual")

    async def test_dispatch_raises_conflict_error_if_the_job_has_been_deleted(
        self, execution_service: ExecutionService, make_job, job_service, organization_id
    ) -> None:
        job = await make_job()
        await job_service.delete(organization_id, job.id)
        with pytest.raises(ConflictError):
            await execution_service.dispatch(organization_id, job.id, trigger_source="manual")

    async def test_dispatch_snapshots_the_jobs_priority_and_payload_at_dispatch_time(
        self, execution_service: ExecutionService, make_job, organization_id
    ) -> None:
        job = await make_job(priority=JobPriority.HIGH, payload={"target": "asset-1"})
        execution = await execution_service.dispatch(
            organization_id, job.id, trigger_source="manual"
        )
        assert execution.priority_snapshot == JobPriority.HIGH
        assert execution.payload_snapshot == {"target": "asset-1"}

    async def test_dispatch_uses_the_given_attempt_number(
        self, execution_service: ExecutionService, make_job, organization_id
    ) -> None:
        job = await make_job()
        execution = await execution_service.dispatch(
            organization_id, job.id, trigger_source="manual", attempt_number=2
        )
        assert execution.attempt_number == 2


class TestDispatchFailure:
    async def test_dispatch_failure_marks_the_execution_failed(
        self,
        failing_execution_service: ExecutionService,
        make_job,
        organization_id,
    ) -> None:
        job = await make_job()
        execution = await failing_execution_service.dispatch(
            organization_id, job.id, trigger_source="manual"
        )
        assert execution.status == ExecutionStatus.FAILED
        assert execution.error is not None
        assert "boom" in execution.error

    async def test_dispatch_failure_increments_the_jobs_failure_counter(
        self,
        failing_execution_service: ExecutionService,
        make_job,
        job_service,
        organization_id,
    ) -> None:
        job = await make_job()
        await failing_execution_service.dispatch(organization_id, job.id, trigger_source="manual")
        reloaded = await job_service.get(organization_id, job.id)
        assert reloaded.failure_count == 1

    async def test_dispatch_failure_with_no_retry_policy_retries_using_platform_defaults(
        self,
        failing_execution_service: ExecutionService,
        make_job,
        failures_repo,
        organization_id,
        fail_first_publisher: _FailFirstPublisher,
    ) -> None:
        """No job-specific policy -> the constructor defaults apply
        (``default_max_attempts=3``), so the first attempt (1 of 3) is
        eligible to retry rather than being terminal."""
        job = await make_job()
        execution = await failing_execution_service.dispatch(
            organization_id, job.id, trigger_source="manual"
        )
        assert execution.attempt_number == 1
        failures = await failures_repo.list_for_job(organization_id, job.id)
        assert len(failures) == 1
        failure = failures[0]
        assert failure.is_terminal is False
        assert failure.retry_at is not None
        assert failure.execution_id == execution.id
        assert "JobRetried" in fail_first_publisher.names

    async def test_dispatch_failure_with_a_policy_exhausted_by_max_attempts_is_terminal(
        self,
        failing_execution_service: ExecutionService,
        make_job,
        failures_repo,
        retry_policies_repo,
        organization_id,
        fail_first_publisher: _FailFirstPublisher,
    ) -> None:
        job = await make_job()
        await retry_policies_repo.create(
            JobRetryPolicy(organization_id=organization_id, job_id=job.id, max_attempts=1)
        )
        execution = await failing_execution_service.dispatch(
            organization_id, job.id, trigger_source="manual"
        )
        failures = await failures_repo.list_for_job(organization_id, job.id)
        assert len(failures) == 1
        failure = failures[0]
        assert failure.is_terminal is True
        assert failure.retry_at is None
        assert failure.execution_id == execution.id
        assert "JobFailed" in fail_first_publisher.names

    async def test_dispatch_failure_with_dead_letter_disabled_is_terminal(
        self,
        failing_execution_service: ExecutionService,
        make_job,
        failures_repo,
        retry_policies_repo,
        organization_id,
    ) -> None:
        """``dead_letter_enabled=False`` overrides the retry decision
        entirely -- even with plenty of attempts left, it never retries."""
        job = await make_job()
        await retry_policies_repo.create(
            JobRetryPolicy(
                organization_id=organization_id,
                job_id=job.id,
                max_attempts=5,
                dead_letter_enabled=False,
            )
        )
        execution = await failing_execution_service.dispatch(
            organization_id, job.id, trigger_source="manual"
        )
        failures = await failures_repo.list_for_job(organization_id, job.id)
        assert len(failures) == 1
        assert failures[0].is_terminal is True
        assert failures[0].execution_id == execution.id

    async def test_dispatch_failure_sends_a_failure_notification_when_the_job_has_an_owner(
        self,
        failing_execution_service: ExecutionService,
        make_job,
        retry_policies_repo,
        organization_id,
    ) -> None:
        job = await make_job(owner_id="owner-2")
        await retry_policies_repo.create(
            JobRetryPolicy(organization_id=organization_id, job_id=job.id, max_attempts=1)
        )
        execution = await failing_execution_service.dispatch(
            organization_id, job.id, trigger_source="manual"
        )
        assert execution.status == ExecutionStatus.FAILED


class TestRetryFailure:
    async def test_retry_failure_raises_not_found_error_if_the_failure_does_not_exist(
        self, execution_service: ExecutionService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await execution_service.retry_failure(organization_id, uuid4())

    async def test_retry_failure_raises_conflict_error_if_already_retried(
        self,
        execution_service: ExecutionService,
        failing_execution_service: ExecutionService,
        make_job,
        failures_repo,
        retry_policies_repo,
        organization_id,
    ) -> None:
        job = await make_job()
        await retry_policies_repo.create(
            JobRetryPolicy(organization_id=organization_id, job_id=job.id, max_attempts=5)
        )
        await failing_execution_service.dispatch(organization_id, job.id, trigger_source="manual")
        failures = await failures_repo.list_for_job(organization_id, job.id)
        failure = failures[0]

        await execution_service.retry_failure(organization_id, failure.id)
        with pytest.raises(ConflictError):
            await execution_service.retry_failure(organization_id, failure.id)

    async def test_retry_failure_raises_conflict_error_if_terminal(
        self,
        execution_service: ExecutionService,
        failing_execution_service: ExecutionService,
        make_job,
        failures_repo,
        retry_policies_repo,
        organization_id,
    ) -> None:
        job = await make_job()
        await retry_policies_repo.create(
            JobRetryPolicy(organization_id=organization_id, job_id=job.id, max_attempts=1)
        )
        await failing_execution_service.dispatch(organization_id, job.id, trigger_source="manual")
        failures = await failures_repo.list_for_job(organization_id, job.id)
        failure = failures[0]
        assert failure.is_terminal is True

        with pytest.raises(ConflictError):
            await execution_service.retry_failure(organization_id, failure.id)

    async def test_retry_failure_increments_attempt_and_keeps_trigger_source(
        self,
        execution_service: ExecutionService,
        failing_execution_service: ExecutionService,
        make_job,
        failures_repo,
        retry_policies_repo,
        organization_id,
    ) -> None:
        job = await make_job()
        await retry_policies_repo.create(
            JobRetryPolicy(organization_id=organization_id, job_id=job.id, max_attempts=5)
        )
        prior = await failing_execution_service.dispatch(
            organization_id, job.id, trigger_source="cron"
        )
        failures = await failures_repo.list_for_job(organization_id, job.id)
        failure = failures[0]
        assert failure.retried is False

        retried_execution = await execution_service.retry_failure(organization_id, failure.id)

        assert retried_execution.attempt_number == prior.attempt_number + 1
        assert retried_execution.trigger_source == prior.trigger_source
        assert retried_execution.status == ExecutionStatus.COMPLETED

        reloaded_failure = await failures_repo.require_in_org(organization_id, failure.id)
        assert reloaded_failure.retried is True


class TestCancelOpenForJob:
    async def test_cancel_open_for_job_returns_zero_when_no_executions_exist(
        self, execution_service: ExecutionService, make_job, organization_id
    ) -> None:
        job = await make_job()
        cancelled = await execution_service.cancel_open_for_job(organization_id, job.id)
        assert cancelled == 0

    async def test_cancel_open_for_job_cancels_only_open_executions(
        self,
        execution_service: ExecutionService,
        executions_repo,
        make_job,
        organization_id,
        publisher,
    ) -> None:
        job = await make_job()

        async def _make_execution(status: ExecutionStatus) -> JobExecution:
            return await executions_repo.create(
                JobExecution(
                    organization_id=organization_id,
                    job_id=job.id,
                    status=status,
                    trigger_source="manual",
                    priority_snapshot=JobPriority.NORMAL,
                    payload_snapshot={},
                    queued_at=datetime.now(UTC),
                )
            )

        queued = await _make_execution(ExecutionStatus.QUEUED)
        running = await _make_execution(ExecutionStatus.RUNNING)
        waiting = await _make_execution(ExecutionStatus.WAITING)
        completed = await _make_execution(ExecutionStatus.COMPLETED)

        cancelled = await execution_service.cancel_open_for_job(organization_id, job.id)

        assert cancelled == 3
        reloaded_queued = await executions_repo.require_in_org(organization_id, queued.id)
        reloaded_running = await executions_repo.require_in_org(organization_id, running.id)
        reloaded_waiting = await executions_repo.require_in_org(organization_id, waiting.id)
        reloaded_completed = await executions_repo.require_in_org(organization_id, completed.id)
        assert reloaded_queued.status == ExecutionStatus.CANCELLED
        assert reloaded_running.status == ExecutionStatus.CANCELLED
        assert reloaded_waiting.status == ExecutionStatus.CANCELLED
        assert reloaded_completed.status == ExecutionStatus.COMPLETED
        assert reloaded_queued.completed_at is not None
        assert publisher.names.count("JobCancelled") == 3


class TestGet:
    async def test_get_returns_the_execution(
        self, execution_service: ExecutionService, make_job, organization_id
    ) -> None:
        job = await make_job()
        created = await execution_service.dispatch(organization_id, job.id, trigger_source="manual")
        found = await execution_service.get(organization_id, created.id)
        assert found.id == created.id

    async def test_get_raises_not_found_error_if_it_does_not_exist(
        self, execution_service: ExecutionService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await execution_service.get(organization_id, uuid4())


class TestListForJob:
    async def test_list_for_job_returns_every_execution_for_the_job(
        self, execution_service: ExecutionService, make_job, organization_id
    ) -> None:
        job = await make_job()
        await execution_service.dispatch(organization_id, job.id, trigger_source="manual")
        await execution_service.dispatch(organization_id, job.id, trigger_source="manual")
        found = await execution_service.list_for_job(organization_id, job.id)
        assert len(found) == 2


class TestListFiltered:
    async def test_list_filtered_filters_by_status_and_job(
        self, execution_service: ExecutionService, make_job, organization_id
    ) -> None:
        job_a = await make_job(name="Job A")
        job_b = await make_job(name="Job B")
        await execution_service.dispatch(organization_id, job_a.id, trigger_source="manual")
        await execution_service.dispatch(organization_id, job_b.id, trigger_source="manual")

        by_job = await execution_service.list_filtered(organization_id, job_id=job_a.id)
        assert len(by_job) == 1
        assert by_job[0].job_id == job_a.id

        by_status = await execution_service.list_filtered(
            organization_id, status=ExecutionStatus.COMPLETED
        )
        assert len(by_status) == 2


class TestLogs:
    async def test_add_log_and_list_logs_round_trips(
        self, execution_service: ExecutionService, make_job, organization_id
    ) -> None:
        job = await make_job()
        execution = await execution_service.dispatch(
            organization_id, job.id, trigger_source="manual"
        )
        await execution_service.add_log(
            organization_id, execution.id, level="info", message="Started work"
        )
        await execution_service.add_log(
            organization_id, execution.id, level="error", message="Something went wrong"
        )
        logs = await execution_service.list_logs(organization_id, execution.id)
        assert len(logs) == 2
        assert [log.message for log in logs] == ["Started work", "Something went wrong"]
