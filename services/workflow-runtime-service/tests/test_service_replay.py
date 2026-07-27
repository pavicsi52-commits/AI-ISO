"""Tests for :class:`app.services.replay.WorkflowReplayService`."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.exceptions.not_found import NotFoundError
from shared_core.queue.factory import QueueFramework
from shared_core.workflow import Checkpoint, WorkflowState, WorkflowTaskQueue
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReplayType, WorkflowInstanceStatus
from app.repositories.workflow_checkpoint import WorkflowCheckpointRepository
from app.repositories.workflow_instance import WorkflowInstanceRepository
from app.repositories.workflow_replay import WorkflowReplayRepository
from app.services.checkpoint import WorkflowCheckpointService
from app.services.replay import WorkflowReplayService
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


def _build_service(
    db_session: AsyncSession, http_client: httpx.AsyncClient, task_queue: WorkflowTaskQueue
) -> WorkflowReplayService:
    published: list[object] = []

    async def _collect(event: object) -> None:
        published.append(event)

    execution = build_execution_service(
        db_session, http_client=http_client, task_queue=task_queue, publish_event=_collect
    )
    return WorkflowReplayService(
        WorkflowReplayRepository(db_session),
        WorkflowInstanceRepository(db_session),
        WorkflowCheckpointRepository(db_session),
        execution,
        publish_event=_collect,
    )


class TestWorkflowReplayService:
    async def test_full_replay_creates_and_runs_new_instance(
        self,
        db_session: AsyncSession,
        http_client: httpx.AsyncClient,
        httpx_mock: HTTPXMock,
        real_queue_framework: QueueFramework,
    ) -> None:
        job_id = str(uuid.uuid4())
        nodes: list[dict[str, Any]] = [
            {"node_id": "start", "node_type": "start", "name": "start"},
            {
                "node_id": "task",
                "node_type": "task",
                "name": "task",
                "config": {"job_id": job_id},
            },
            {"node_id": "end", "node_type": "end", "name": "end"},
        ]
        edges = [
            {"from_node_id": "start", "to_node_id": "task"},
            {"from_node_id": "task", "to_node_id": "end"},
        ]
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

        definition = await make_definition(db_session)
        version = await make_version(db_session, definition, nodes=nodes, edges=edges)
        instance = await make_instance(db_session, definition, version)

        task_queue = WorkflowTaskQueue(real_queue_framework.manager)
        await task_queue.declare()
        service = _build_service(db_session, http_client, task_queue)

        record = await service.replay(
            instance.id,
            replay_type=ReplayType.FULL,
            checkpoint_id=None,
            requested_by=uuid.uuid4(),
            caller_token="tok",
        )

        assert record.replay_type == ReplayType.FULL
        assert record.new_instance_id != instance.id

        new_instance = await WorkflowInstanceRepository(db_session).require_by_id(
            record.new_instance_id
        )
        assert new_instance.status == WorkflowInstanceStatus.COMPLETED

    async def test_replay_from_checkpoint_seeds_variables(
        self,
        db_session: AsyncSession,
        http_client: httpx.AsyncClient,
        httpx_mock: HTTPXMock,
        real_queue_framework: QueueFramework,
    ) -> None:
        nodes: list[dict[str, Any]] = [
            {"node_id": "start", "node_type": "start", "name": "start"},
            {"node_id": "end", "node_type": "end", "name": "end"},
        ]
        edges = [{"from_node_id": "start", "to_node_id": "end"}]

        definition = await make_definition(db_session)
        version = await make_version(db_session, definition, nodes=nodes, edges=edges)
        instance = await make_instance(db_session, definition, version)

        checkpoint_service = WorkflowCheckpointService(WorkflowCheckpointRepository(db_session))
        stored = await checkpoint_service.persist(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            checkpoint=Checkpoint(
                execution_id=str(instance.id),
                state=WorkflowState.RUNNING,
                completed_node_ids=("start",),
                variables_snapshot={"seeded": True},
                created_at=datetime.now(UTC),
            ),
        )

        task_queue = WorkflowTaskQueue(real_queue_framework.manager)
        await task_queue.declare()
        service = _build_service(db_session, http_client, task_queue)

        record = await service.replay(
            instance.id,
            replay_type=ReplayType.FROM_CHECKPOINT,
            checkpoint_id=stored.id,
            requested_by=None,
            caller_token="tok",
        )
        assert record.source_checkpoint_id == stored.id

    async def test_replay_from_checkpoint_missing_raises(
        self,
        db_session: AsyncSession,
        http_client: httpx.AsyncClient,
        real_queue_framework: QueueFramework,
    ) -> None:
        nodes: list[dict[str, Any]] = [
            {"node_id": "start", "node_type": "start", "name": "start"},
            {"node_id": "end", "node_type": "end", "name": "end"},
        ]
        edges = [{"from_node_id": "start", "to_node_id": "end"}]
        definition = await make_definition(db_session)
        version = await make_version(db_session, definition, nodes=nodes, edges=edges)
        instance = await make_instance(db_session, definition, version)

        task_queue = WorkflowTaskQueue(real_queue_framework.manager)
        await task_queue.declare()
        service = _build_service(db_session, http_client, task_queue)

        with pytest.raises(NotFoundError):
            await service.replay(
                instance.id,
                replay_type=ReplayType.FROM_CHECKPOINT,
                checkpoint_id=None,
                requested_by=None,
                caller_token="tok",
            )

    async def test_list_for_instance(
        self,
        db_session: AsyncSession,
        http_client: httpx.AsyncClient,
        httpx_mock: HTTPXMock,
        real_queue_framework: QueueFramework,
    ) -> None:
        nodes: list[dict[str, Any]] = [
            {"node_id": "start", "node_type": "start", "name": "start"},
            {"node_id": "end", "node_type": "end", "name": "end"},
        ]
        edges = [{"from_node_id": "start", "to_node_id": "end"}]
        definition = await make_definition(db_session)
        version = await make_version(db_session, definition, nodes=nodes, edges=edges)
        instance = await make_instance(db_session, definition, version)

        task_queue = WorkflowTaskQueue(real_queue_framework.manager)
        await task_queue.declare()
        service = _build_service(db_session, http_client, task_queue)
        await service.replay(
            instance.id,
            replay_type=ReplayType.FULL,
            checkpoint_id=None,
            requested_by=None,
            caller_token="tok",
        )

        replays = await service.list_for_instance(instance.id)
        assert len(replays) == 1
