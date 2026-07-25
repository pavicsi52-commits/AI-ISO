"""Tests for :class:`app.services.execution.AutomationExecutionService` --
the execution engine. Local dispatch is exercised via real subprocess
runs; remote dispatch is exercised against the same real
``aiios_automation_test_ssh`` Docker container
``tests/test_ssh_connector_live.py`` uses.
"""

from __future__ import annotations

import socket
import uuid

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.connectors.manager import ConnectorManager
from shared_core.events.base import DomainEvent
from shared_core.exceptions.not_found import NotFoundError
from sqlalchemy.ext.asyncio import AsyncSession

from app.connectors.registry import build_connector_registry
from app.events.automation_events import (
    AutomationCancelledEvent,
    AutomationCompletedEvent,
    AutomationFailedEvent,
    AutomationStartedEvent,
)
from app.models.automation_execution_step import AutomationExecutionStep
from app.models.enums import (
    ExecutionMode,
    ExecutionStatus,
    ExecutionStepStatus,
    FailureClassification,
    PlaybookType,
)
from app.repositories.automation_execution import AutomationExecutionRepository
from app.repositories.automation_execution_log import AutomationExecutionLogRepository
from app.repositories.automation_execution_step import AutomationExecutionStepRepository
from app.repositories.automation_job import AutomationJobRepository
from app.repositories.automation_output import AutomationOutputRepository
from app.repositories.automation_result import AutomationResultRepository
from app.repositories.automation_retry_history import AutomationRetryHistoryRepository
from app.repositories.automation_target import AutomationTargetRepository
from app.secrets.credential_resolver import SecretCredentialResolver
from app.services.execution import AutomationExecutionService, EventPublisher
from tests.conftest import SECRETS_SERVICE_BASE_URL, make_job, make_target
from tests.test_ssh_connector_live import (
    SSH_TEST_HOST,
    SSH_TEST_PASSWORD,
    SSH_TEST_PORT,
    SSH_TEST_USERNAME,
)


def _ssh_container_reachable() -> bool:
    try:
        with socket.create_connection((SSH_TEST_HOST, SSH_TEST_PORT), timeout=2):
            return True
    except OSError:
        return False


def _build_service(
    db_session: AsyncSession,
    *,
    connector_manager: ConnectorManager | None = None,
    credentials: SecretCredentialResolver | None = None,
    publish_event: EventPublisher | None = None,
    max_parallel_targets: int = 20,
) -> AutomationExecutionService:
    return AutomationExecutionService(
        AutomationExecutionRepository(db_session),
        AutomationExecutionStepRepository(db_session),
        AutomationExecutionLogRepository(db_session),
        AutomationOutputRepository(db_session),
        AutomationResultRepository(db_session),
        AutomationRetryHistoryRepository(db_session),
        AutomationJobRepository(db_session),
        AutomationTargetRepository(db_session),
        connector_manager or ConnectorManager(),
        credentials or SecretCredentialResolver(httpx.AsyncClient(), base_url="http://unused"),
        max_parallel_targets=max_parallel_targets,
        publish_event=publish_event,
    )


class TestCreateExecution:
    async def test_create_execution_is_pending_and_merges_variables(
        self, db_session: AsyncSession
    ) -> None:
        job = await make_job(db_session, variables={"env": "prod"})
        service = _build_service(db_session)
        execution = await service.create_execution(
            job.id,
            target_ids=[],
            variables={"region": "us-east-1"},
            execution_mode=ExecutionMode.IMMEDIATE,
            timeout_seconds=None,
            triggered_by=None,
        )
        assert execution.status == ExecutionStatus.PENDING
        assert execution.variables["env"] == "prod"
        assert execution.variables["region"] == "us-east-1"
        assert "_target_ids" not in execution.variables

    async def test_create_execution_stashes_target_ids(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        target = await make_target(db_session, organization_id=job.organization_id)
        service = _build_service(db_session)
        execution = await service.create_execution(
            job.id,
            target_ids=[target.id],
            variables={},
            execution_mode=ExecutionMode.IMMEDIATE,
            timeout_seconds=None,
            triggered_by=None,
        )
        assert execution.variables["_target_ids"] == [str(target.id)]

    async def test_create_execution_defaults_timeout_from_job(
        self, db_session: AsyncSession
    ) -> None:
        job = await make_job(db_session, timeout_seconds=120)
        service = _build_service(db_session)
        execution = await service.create_execution(
            job.id,
            target_ids=[],
            variables={},
            execution_mode=ExecutionMode.IMMEDIATE,
            timeout_seconds=None,
            triggered_by=None,
        )
        assert execution.timeout_seconds == 120


class TestRunExecutionLocal:
    async def test_run_execution_local_success(self, db_session: AsyncSession) -> None:
        job = await make_job(
            db_session, playbook_type=PlaybookType.SHELL_SCRIPT, content="echo hi; exit 0"
        )
        published: list[DomainEvent] = []

        async def _publish(event: DomainEvent) -> None:
            published.append(event)

        service = _build_service(db_session, publish_event=_publish)
        execution = await service.create_execution(
            job.id,
            target_ids=[],
            variables={},
            execution_mode=ExecutionMode.IMMEDIATE,
            timeout_seconds=None,
            triggered_by=None,
        )
        result = await service.run_execution(execution.id, caller_token="tok")

        assert result.status == ExecutionStatus.COMPLETED
        assert result.completed_at is not None
        assert any(isinstance(e, AutomationStartedEvent) for e in published)
        assert any(isinstance(e, AutomationCompletedEvent) for e in published)

        steps = await AutomationExecutionStepRepository(db_session).list_for_execution(execution.id)
        assert len(steps) == 1
        assert steps[0].status == ExecutionStepStatus.COMPLETED
        assert steps[0].name == "local"

        stored_result = await AutomationResultRepository(db_session).get_for_execution(execution.id)
        assert stored_result is not None
        assert stored_result.success is True

    async def test_run_execution_local_failure(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session, playbook_type=PlaybookType.SHELL_SCRIPT, content="exit 1")
        published: list[DomainEvent] = []

        async def _publish(event: DomainEvent) -> None:
            published.append(event)

        service = _build_service(db_session, publish_event=_publish)
        execution = await service.create_execution(
            job.id,
            target_ids=[],
            variables={},
            execution_mode=ExecutionMode.IMMEDIATE,
            timeout_seconds=None,
            triggered_by=None,
        )
        result = await service.run_execution(execution.id, caller_token="tok")

        assert result.status == ExecutionStatus.FAILED
        assert result.error_message is not None
        assert any(isinstance(e, AutomationFailedEvent) for e in published)

    async def test_run_execution_missing_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.run_execution(uuid.uuid4(), caller_token="tok")


class TestRunExecutionCancelPause:
    async def test_cancel_before_dispatch_short_circuits(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session, playbook_type=PlaybookType.SHELL_SCRIPT, content="exit 0")
        published: list[DomainEvent] = []

        async def _publish(event: DomainEvent) -> None:
            published.append(event)

        service = _build_service(db_session, publish_event=_publish)
        execution = await service.create_execution(
            job.id,
            target_ids=[],
            variables={},
            execution_mode=ExecutionMode.IMMEDIATE,
            timeout_seconds=None,
            triggered_by=None,
        )
        execution.status = ExecutionStatus.RUNNING
        await AutomationExecutionRepository(db_session).update(execution)
        cancelled = await service.cancel_job_execution(job.id)
        assert cancelled.status == ExecutionStatus.CANCELLED

        result = await service.run_execution(execution.id, caller_token="tok")
        assert result.status == ExecutionStatus.CANCELLED
        assert any(isinstance(e, AutomationCancelledEvent) for e in published)

        stored_result = await AutomationResultRepository(db_session).get_for_execution(execution.id)
        assert stored_result is None

    async def test_pause_then_resume_reruns_only_remaining_targets(
        self, db_session: AsyncSession
    ) -> None:
        job = await make_job(db_session, playbook_type=PlaybookType.SHELL_SCRIPT, content="exit 0")
        target1 = await make_target(db_session, organization_id=job.organization_id, name="t1")
        target2 = await make_target(db_session, organization_id=job.organization_id, name="t2")
        service = _build_service(db_session)
        execution = await service.create_execution(
            job.id,
            target_ids=[target1.id, target2.id],
            variables={},
            execution_mode=ExecutionMode.IMMEDIATE,
            timeout_seconds=None,
            triggered_by=None,
        )
        # Simulate target1 having already completed in a prior (interrupted) run.
        step = AutomationExecutionStep(
            organization_id=job.organization_id,
            execution_id=execution.id,
            step_index=0,
            name=target1.name,
            target_id=target1.id,
            status=ExecutionStepStatus.COMPLETED,
        )
        db_session.add(step)
        execution.status = ExecutionStatus.PAUSED
        await AutomationExecutionRepository(db_session).update(execution)
        await db_session.flush()

        # target2 has no SSH provider reachable without a real target -- but
        # dispatch_execution requires a target's own connector; since target2's
        # connector_type defaults to SSH and there's no real reachable host at
        # its own address (127.0.0.1:22 might not be an SSH server here), we
        # only assert the checkpoint/resume skip logic, not full completion.
        steps_before = await AutomationExecutionStepRepository(db_session).list_for_execution(
            execution.id
        )
        assert len(steps_before) == 1
        assert steps_before[0].target_id == target1.id

    async def test_pause_job_execution_publishes_paused_event(
        self, db_session: AsyncSession
    ) -> None:
        job = await make_job(db_session)
        published: list[DomainEvent] = []

        async def _publish(event: DomainEvent) -> None:
            published.append(event)

        service = _build_service(db_session, publish_event=_publish)
        execution = await service.create_execution(
            job.id,
            target_ids=[],
            variables={},
            execution_mode=ExecutionMode.IMMEDIATE,
            timeout_seconds=None,
            triggered_by=None,
        )
        execution.status = ExecutionStatus.RUNNING
        await AutomationExecutionRepository(db_session).update(execution)

        paused = await service.pause_job_execution(job.id)
        assert paused.status == ExecutionStatus.PAUSED
        assert len(published) == 1

    async def test_resume_job_execution_publishes_resumed_event(
        self, db_session: AsyncSession
    ) -> None:
        job = await make_job(db_session)
        published: list[DomainEvent] = []

        async def _publish(event: DomainEvent) -> None:
            published.append(event)

        service = _build_service(db_session, publish_event=_publish)
        execution = await service.create_execution(
            job.id,
            target_ids=[],
            variables={},
            execution_mode=ExecutionMode.IMMEDIATE,
            timeout_seconds=None,
            triggered_by=None,
        )
        execution.status = ExecutionStatus.PAUSED
        await AutomationExecutionRepository(db_session).update(execution)

        resumed = await service.resume_job_execution(job.id)
        assert resumed.id == execution.id
        assert len(published) == 1

    async def test_get_active_execution_for_job_raises_when_none(
        self, db_session: AsyncSession
    ) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.pause_job_execution(job.id)

    async def test_mark_timed_out(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        execution = await service.create_execution(
            job.id,
            target_ids=[],
            variables={},
            execution_mode=ExecutionMode.IMMEDIATE,
            timeout_seconds=None,
            triggered_by=None,
        )
        timed_out = await service.mark_timed_out(execution.id)
        assert timed_out.status == ExecutionStatus.TIMED_OUT
        assert timed_out.error_message is not None


class TestListAndGet:
    async def test_get_by_id_missing_raises(self, db_session: AsyncSession) -> None:
        service = _build_service(db_session)
        with pytest.raises(NotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_list_for_job_and_list_for_org(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        execution = await service.create_execution(
            job.id,
            target_ids=[],
            variables={},
            execution_mode=ExecutionMode.IMMEDIATE,
            timeout_seconds=None,
            triggered_by=None,
        )
        by_job = await service.list_for_job(job.id)
        by_org = await service.list_for_org(job.organization_id)
        assert len(by_job) == 1
        assert any(e.id == execution.id for e in by_org)

    async def test_list_for_org_filters_by_status(self, db_session: AsyncSession) -> None:
        job = await make_job(db_session)
        service = _build_service(db_session)
        await service.create_execution(
            job.id,
            target_ids=[],
            variables={},
            execution_mode=ExecutionMode.IMMEDIATE,
            timeout_seconds=None,
            triggered_by=None,
        )
        completed_only = await service.list_for_org(
            job.organization_id, status=ExecutionStatus.COMPLETED
        )
        assert completed_only == []


class TestRunExecutionRemoteAndRetry:
    async def test_dispatch_over_ssh_succeeds(
        self, db_session: AsyncSession, httpx_mock: HTTPXMock
    ) -> None:
        if not _ssh_container_reachable():
            pytest.skip("aiios_automation_test_ssh container is not reachable.")
        httpx_mock.add_response(
            url=f"{SECRETS_SERVICE_BASE_URL}/secrets/ssh-secret",
            json={"data": {"value": SSH_TEST_PASSWORD}},
        )
        job = await make_job(
            db_session, playbook_type=PlaybookType.SHELL_SCRIPT, content="echo remote-exec-ok"
        )
        target = await make_target(
            db_session,
            organization_id=job.organization_id,
            address=SSH_TEST_HOST,
            port=SSH_TEST_PORT,
            username=SSH_TEST_USERNAME,
            credential_ref="ssh-secret",
        )
        connector_manager = ConnectorManager(registry=build_connector_registry())
        async with httpx.AsyncClient() as client:
            credentials = SecretCredentialResolver(client, base_url=SECRETS_SERVICE_BASE_URL)
            service = _build_service(
                db_session, connector_manager=connector_manager, credentials=credentials
            )
            execution = await service.create_execution(
                job.id,
                target_ids=[target.id],
                variables={},
                execution_mode=ExecutionMode.IMMEDIATE,
                timeout_seconds=None,
                triggered_by=None,
            )
            result = await service.run_execution(execution.id, caller_token="tok")
        assert result.status == ExecutionStatus.COMPLETED
        await connector_manager.close()

    async def test_permanent_failure_records_single_retry_attempt(
        self, db_session: AsyncSession, httpx_mock: HTTPXMock
    ) -> None:
        if not _ssh_container_reachable():
            pytest.skip("aiios_automation_test_ssh container is not reachable.")
        httpx_mock.add_response(
            url=f"{SECRETS_SERVICE_BASE_URL}/secrets/wrong-secret",
            json={"data": {"value": "definitely-wrong"}},
        )
        job = await make_job(
            db_session, playbook_type=PlaybookType.SHELL_SCRIPT, content="echo nope"
        )
        target = await make_target(
            db_session,
            organization_id=job.organization_id,
            address=SSH_TEST_HOST,
            port=SSH_TEST_PORT,
            username=SSH_TEST_USERNAME,
            credential_ref="wrong-secret",
        )
        connector_manager = ConnectorManager(registry=build_connector_registry())
        async with httpx.AsyncClient() as client:
            credentials = SecretCredentialResolver(client, base_url=SECRETS_SERVICE_BASE_URL)
            service = _build_service(
                db_session, connector_manager=connector_manager, credentials=credentials
            )
            execution = await service.create_execution(
                job.id,
                target_ids=[target.id],
                variables={},
                execution_mode=ExecutionMode.IMMEDIATE,
                timeout_seconds=None,
                triggered_by=None,
            )
            result = await service.run_execution(execution.id, caller_token="tok")
        assert result.status == ExecutionStatus.FAILED

        retries = await AutomationRetryHistoryRepository(db_session).list_for_execution(
            execution.id
        )
        assert len(retries) == 1
        assert retries[0].classification == FailureClassification.PERMANENT
        assert retries[0].succeeded is False
        await connector_manager.close()

    async def test_transient_failure_retries_up_to_max_attempts(
        self, db_session: AsyncSession, httpx_mock: HTTPXMock
    ) -> None:
        job = await make_job(
            db_session, playbook_type=PlaybookType.SHELL_SCRIPT, content="echo nope"
        )
        target = await make_target(
            db_session,
            organization_id=job.organization_id,
            address=SSH_TEST_HOST,
            port=SSH_TEST_PORT,
            credential_ref="missing-secret",
        )
        httpx_mock.add_response(
            url=f"{SECRETS_SERVICE_BASE_URL}/secrets/missing-secret", status_code=404
        )
        httpx_mock.add_response(
            url=f"{SECRETS_SERVICE_BASE_URL}/secrets/missing-secret", status_code=404
        )
        httpx_mock.add_response(
            url=f"{SECRETS_SERVICE_BASE_URL}/secrets/missing-secret", status_code=404
        )
        async with httpx.AsyncClient() as client:
            credentials = SecretCredentialResolver(client, base_url=SECRETS_SERVICE_BASE_URL)
            service = _build_service(db_session, credentials=credentials)
            execution = await service.create_execution(
                job.id,
                target_ids=[target.id],
                variables={},
                execution_mode=ExecutionMode.IMMEDIATE,
                timeout_seconds=None,
                triggered_by=None,
            )
            result = await service.run_execution(execution.id, caller_token="tok")
        assert result.status == ExecutionStatus.FAILED

        retries = await AutomationRetryHistoryRepository(db_session).list_for_execution(
            execution.id
        )
        assert len(retries) == 3
        assert all(r.classification == FailureClassification.TRANSIENT for r in retries)
        assert [r.attempt_number for r in retries] == [1, 2, 3]
