"""Tests for :func:`app.workers.execution_worker.build_execution_worker`."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
import pytest
from shared_core.connectors.manager import ConnectorManager
from shared_core.exceptions.database import DatabaseError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ExecutionMode, ExecutionStatus, PlaybookType
from app.repositories.automation_execution import AutomationExecutionRepository
from app.repositories.automation_execution_log import AutomationExecutionLogRepository
from app.repositories.automation_execution_step import AutomationExecutionStepRepository
from app.repositories.automation_job import AutomationJobRepository
from app.repositories.automation_output import AutomationOutputRepository
from app.repositories.automation_result import AutomationResultRepository
from app.repositories.automation_retry_history import AutomationRetryHistoryRepository
from app.repositories.automation_target import AutomationTargetRepository
from app.secrets.credential_resolver import SecretCredentialResolver
from app.services.execution import AutomationExecutionService
from app.workers.execution_worker import build_execution_worker
from tests.conftest import make_job


def _build_execution_service(db_session: AsyncSession) -> AutomationExecutionService:
    return AutomationExecutionService(
        AutomationExecutionRepository(db_session),
        AutomationExecutionStepRepository(db_session),
        AutomationExecutionLogRepository(db_session),
        AutomationOutputRepository(db_session),
        AutomationResultRepository(db_session),
        AutomationRetryHistoryRepository(db_session),
        AutomationJobRepository(db_session),
        AutomationTargetRepository(db_session),
        ConnectorManager(),
        SecretCredentialResolver(httpx.AsyncClient(), base_url="http://unused"),
    )


async def test_execution_worker_runs_execution_to_completion(db_session: AsyncSession) -> None:
    job = await make_job(db_session, playbook_type=PlaybookType.SHELL_SCRIPT, content="exit 0")
    executions = _build_execution_service(db_session)
    execution = await executions.create_execution(
        job.id,
        target_ids=[],
        variables={},
        execution_mode=ExecutionMode.IMMEDIATE,
        timeout_seconds=None,
        triggered_by=None,
    )

    @asynccontextmanager
    async def factory() -> AsyncIterator[AutomationExecutionService]:
        yield executions

    handler = build_execution_worker(factory)
    await handler({"execution_id": str(execution.id), "caller_token": "tok"})

    refetched = await AutomationExecutionRepository(db_session).require_by_id(execution.id)
    assert refetched.status == ExecutionStatus.COMPLETED


async def test_execution_worker_skips_when_no_caller_token(db_session: AsyncSession) -> None:
    job = await make_job(db_session, playbook_type=PlaybookType.SHELL_SCRIPT, content="exit 0")
    executions = _build_execution_service(db_session)
    execution = await executions.create_execution(
        job.id,
        target_ids=[],
        variables={},
        execution_mode=ExecutionMode.IMMEDIATE,
        timeout_seconds=None,
        triggered_by=None,
    )

    @asynccontextmanager
    async def factory() -> AsyncIterator[AutomationExecutionService]:
        yield executions

    handler = build_execution_worker(factory)
    await handler({"execution_id": str(execution.id), "caller_token": None})

    refetched = await AutomationExecutionRepository(db_session).require_by_id(execution.id)
    assert refetched.status == ExecutionStatus.PENDING


async def test_execution_worker_reraises_on_failure() -> None:
    @asynccontextmanager
    async def failing_factory() -> AsyncIterator[AutomationExecutionService]:
        raise DatabaseError("boom")
        yield  # pragma: no cover -- unreachable, satisfies generator shape

    handler = build_execution_worker(failing_factory)
    with pytest.raises(DatabaseError):
        await handler({"execution_id": str(uuid.uuid4()), "caller_token": "tok"})
