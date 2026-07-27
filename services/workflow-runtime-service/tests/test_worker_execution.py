"""Tests for :func:`app.workers.execution_worker.build_execution_worker`."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.exceptions.database import DatabaseError
from shared_core.queue.factory import QueueFramework
from shared_core.workflow import WorkflowTaskQueue
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import WorkflowInstanceStatus
from app.repositories.workflow_instance import WorkflowInstanceRepository
from app.services.execution import WorkflowExecutionService
from app.workers.execution_worker import build_execution_worker
from tests.conftest import (
    AUTOMATION_SERVICE_BASE_URL,
    build_execution_service,
    make_definition,
    make_instance,
    make_version,
)


@pytest.fixture
async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


async def test_execution_worker_runs_instance_to_completion(
    db_session: AsyncSession,
    http_client: httpx.AsyncClient,
    httpx_mock: HTTPXMock,
    real_queue_framework: QueueFramework,
) -> None:
    job_id = str(uuid.uuid4())
    execution_id = str(uuid.uuid4())
    httpx_mock.add_response(
        url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/jobs/{job_id}/execute",
        method="POST",
        status_code=201,
        json={"data": {"id": execution_id, "status": "pending"}},
    )
    httpx_mock.add_response(
        url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/executions/{execution_id}",
        json={"data": {"id": execution_id, "status": "completed"}},
    )

    nodes: list[dict[str, Any]] = [
        {"node_id": "start", "node_type": "start", "name": "start"},
        {"node_id": "task", "node_type": "task", "name": "task", "config": {"job_id": job_id}},
        {"node_id": "end", "node_type": "end", "name": "end"},
    ]
    edges = [
        {"from_node_id": "start", "to_node_id": "task"},
        {"from_node_id": "task", "to_node_id": "end"},
    ]
    definition = await make_definition(db_session)
    version = await make_version(db_session, definition, nodes=nodes, edges=edges)
    instance = await make_instance(db_session, definition, version)

    task_queue = WorkflowTaskQueue(real_queue_framework.manager)
    await task_queue.declare()
    execution = build_execution_service(db_session, http_client=http_client, task_queue=task_queue)

    @asynccontextmanager
    async def factory() -> AsyncIterator[WorkflowExecutionService]:
        yield execution

    handler = build_execution_worker(factory)
    await handler({"instance_id": str(instance.id), "caller_token": "tok"})

    refetched = await WorkflowInstanceRepository(db_session).require_by_id(instance.id)
    assert refetched.status == WorkflowInstanceStatus.COMPLETED


async def test_execution_worker_skips_when_no_caller_token(db_session: AsyncSession) -> None:
    definition = await make_definition(db_session)
    version = await make_version(db_session, definition)
    instance = await make_instance(db_session, definition, version)

    @asynccontextmanager
    async def factory() -> AsyncIterator[WorkflowExecutionService]:
        raise AssertionError("should never be reached when caller_token is missing")
        yield  # pragma: no cover -- unreachable, satisfies generator shape

    handler = build_execution_worker(factory)
    await handler({"instance_id": str(instance.id), "caller_token": None})

    refetched = await WorkflowInstanceRepository(db_session).require_by_id(instance.id)
    assert refetched.status == WorkflowInstanceStatus.QUEUED


async def test_execution_worker_reraises_on_failure() -> None:
    @asynccontextmanager
    async def failing_factory() -> AsyncIterator[WorkflowExecutionService]:
        raise DatabaseError("boom")
        yield  # pragma: no cover -- unreachable, satisfies generator shape

    handler = build_execution_worker(failing_factory)
    with pytest.raises(DatabaseError):
        await handler({"instance_id": str(uuid.uuid4()), "caller_token": "tok"})
