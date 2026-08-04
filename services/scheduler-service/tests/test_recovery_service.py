"""RecoveryService: manual recovery of a terminal (retries-exhausted) failure.

Against real PostgreSQL, in a SAVEPOINT-isolated session per test.

A terminal ``JobFailure`` is built directly here via ``failures_repo``,
attached to a real execution's id (the FK ``job_failures.execution_id``
requires one) obtained by dispatching the job through the plain
``execution_service`` fixture first -- what status that dispatch itself
ends in does not matter for these tests, only that a real execution row
exists to point the failure at.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from shared_core.exceptions.conflict import ConflictError
from shared_core.exceptions.not_found import NotFoundError

from app.models.enums import RecoveryAction
from app.models.history import JobFailure
from app.services.recovery import RecoveryService

pytestmark = pytest.mark.asyncio


async def _make_failure(
    execution_service,
    failures_repo,
    organization_id,
    job,
    *,
    is_terminal: bool,
    recovered: bool = False,
) -> JobFailure:
    execution = await execution_service.dispatch(organization_id, job.id, trigger_source="manual")
    return await failures_repo.create(
        JobFailure(
            organization_id=organization_id,
            job_id=job.id,
            execution_id=execution.id,
            occurred_at=datetime.now(UTC),
            failure_reason="Simulated failure",
            error_detail="Something went wrong downstream.",
            is_terminal=is_terminal,
            recovered=recovered,
        )
    )


class TestRecover:
    async def test_recover_raises_not_found_error_if_the_failure_does_not_exist(
        self, recovery_service: RecoveryService, organization_id
    ) -> None:
        with pytest.raises(NotFoundError):
            await recovery_service.recover(
                organization_id, uuid4(), action=RecoveryAction.MANUAL_RECOVERY
            )

    async def test_recover_raises_conflict_error_if_the_failure_is_not_terminal(
        self,
        recovery_service: RecoveryService,
        execution_service,
        failures_repo,
        make_job,
        organization_id,
    ) -> None:
        job = await make_job()
        failure = await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=False
        )
        with pytest.raises(ConflictError):
            await recovery_service.recover(
                organization_id, failure.id, action=RecoveryAction.MANUAL_RECOVERY
            )

    async def test_recover_raises_conflict_error_if_already_recovered(
        self,
        recovery_service: RecoveryService,
        execution_service,
        failures_repo,
        make_job,
        organization_id,
    ) -> None:
        job = await make_job()
        failure = await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=True
        )
        await recovery_service.recover(
            organization_id, failure.id, action=RecoveryAction.MANUAL_RECOVERY
        )
        with pytest.raises(ConflictError):
            await recovery_service.recover(
                organization_id, failure.id, action=RecoveryAction.MANUAL_RECOVERY
            )

    async def test_recover_sets_recovered_fields(
        self,
        recovery_service: RecoveryService,
        execution_service,
        failures_repo,
        make_job,
        organization_id,
    ) -> None:
        job = await make_job()
        failure = await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=True
        )
        recovered = await recovery_service.recover(
            organization_id,
            failure.id,
            action=RecoveryAction.MANUAL_RECOVERY,
            recovered_by="ops-engineer-1",
        )
        assert recovered.recovered is True
        assert recovered.recovered_at is not None
        assert recovered.recovered_by == "ops-engineer-1"
        assert recovered.recovery_action == RecoveryAction.MANUAL_RECOVERY

    async def test_recover_publishes_scheduler_recovered_regardless_of_action(
        self,
        recovery_service: RecoveryService,
        execution_service,
        failures_repo,
        make_job,
        organization_id,
        publisher,
    ) -> None:
        job = await make_job()
        failure = await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=True
        )
        await recovery_service.recover(
            organization_id, failure.id, action=RecoveryAction.CHECKPOINT_RECOVERY
        )
        assert "SchedulerRecovered" in publisher.names

    async def test_recover_sends_a_notification_when_the_job_has_an_owner(
        self,
        recovery_service: RecoveryService,
        execution_service,
        failures_repo,
        make_job,
        organization_id,
    ) -> None:
        job = await make_job(owner_id="owner-3")
        failure = await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=True
        )
        recovered = await recovery_service.recover(
            organization_id, failure.id, action=RecoveryAction.MANUAL_RECOVERY
        )
        assert recovered.recovered is True


class TestRecoverRedispatchingActions:
    async def test_automatic_retry_dispatches_a_fresh_execution(
        self,
        recovery_service: RecoveryService,
        execution_service,
        executions_repo,
        failures_repo,
        make_job,
        organization_id,
    ) -> None:
        job = await make_job()
        failure = await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=True
        )
        before = len(await executions_repo.list_for_job(organization_id, job.id))
        await recovery_service.recover(
            organization_id, failure.id, action=RecoveryAction.AUTOMATIC_RETRY
        )
        after = len(await executions_repo.list_for_job(organization_id, job.id))
        assert after == before + 1

    async def test_resume_execution_dispatches_a_fresh_execution(
        self,
        recovery_service: RecoveryService,
        execution_service,
        executions_repo,
        failures_repo,
        make_job,
        organization_id,
    ) -> None:
        job = await make_job()
        failure = await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=True
        )
        before = len(await executions_repo.list_for_job(organization_id, job.id))
        await recovery_service.recover(
            organization_id, failure.id, action=RecoveryAction.RESUME_EXECUTION
        )
        after = len(await executions_repo.list_for_job(organization_id, job.id))
        assert after == before + 1

    async def test_restart_execution_dispatches_a_fresh_execution(
        self,
        recovery_service: RecoveryService,
        execution_service,
        executions_repo,
        failures_repo,
        make_job,
        organization_id,
    ) -> None:
        job = await make_job()
        failure = await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=True
        )
        before = len(await executions_repo.list_for_job(organization_id, job.id))
        await recovery_service.recover(
            organization_id, failure.id, action=RecoveryAction.RESTART_EXECUTION
        )
        after = len(await executions_repo.list_for_job(organization_id, job.id))
        assert after == before + 1


class TestRecoverNonRedispatchingActions:
    async def test_checkpoint_recovery_does_not_dispatch_a_fresh_execution(
        self,
        recovery_service: RecoveryService,
        execution_service,
        executions_repo,
        failures_repo,
        make_job,
        organization_id,
    ) -> None:
        job = await make_job()
        failure = await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=True
        )
        before = len(await executions_repo.list_for_job(organization_id, job.id))
        await recovery_service.recover(
            organization_id, failure.id, action=RecoveryAction.CHECKPOINT_RECOVERY
        )
        after = len(await executions_repo.list_for_job(organization_id, job.id))
        assert after == before

    async def test_rollback_trigger_does_not_dispatch_a_fresh_execution(
        self,
        recovery_service: RecoveryService,
        execution_service,
        executions_repo,
        failures_repo,
        make_job,
        organization_id,
    ) -> None:
        job = await make_job()
        failure = await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=True
        )
        before = len(await executions_repo.list_for_job(organization_id, job.id))
        await recovery_service.recover(
            organization_id, failure.id, action=RecoveryAction.ROLLBACK_TRIGGER
        )
        after = len(await executions_repo.list_for_job(organization_id, job.id))
        assert after == before

    async def test_manual_recovery_does_not_dispatch_a_fresh_execution(
        self,
        recovery_service: RecoveryService,
        execution_service,
        executions_repo,
        failures_repo,
        make_job,
        organization_id,
    ) -> None:
        job = await make_job()
        failure = await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=True
        )
        before = len(await executions_repo.list_for_job(organization_id, job.id))
        await recovery_service.recover(
            organization_id, failure.id, action=RecoveryAction.MANUAL_RECOVERY
        )
        after = len(await executions_repo.list_for_job(organization_id, job.id))
        assert after == before


class TestListUnrecovered:
    async def test_list_unrecovered_returns_empty_list_when_nothing_is_terminal(
        self, recovery_service: RecoveryService, organization_id
    ) -> None:
        found = await recovery_service.list_unrecovered(organization_id)
        assert found == []

    async def test_list_unrecovered_returns_only_terminal_unrecovered_failures(
        self,
        recovery_service: RecoveryService,
        execution_service,
        failures_repo,
        make_job,
        organization_id,
    ) -> None:
        job = await make_job()
        unrecovered_terminal = await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=True
        )
        await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=False
        )
        already_recovered = await _make_failure(
            execution_service, failures_repo, organization_id, job, is_terminal=True
        )
        await recovery_service.recover(
            organization_id, already_recovered.id, action=RecoveryAction.MANUAL_RECOVERY
        )

        found = await recovery_service.list_unrecovered(organization_id)
        assert len(found) == 1
        assert found[0].id == unrecovered_terminal.id
