"""Tests for :class:`app.services.execution.WorkflowExecutionService` --
real end-to-end ``shared_core.workflow.WorkflowEngine.run()`` calls, no
mocking of the DAG engine itself. ``TASK``/``CONNECTOR`` dispatch uses
``pytest-httpx`` against the Automation Service's own real documented
response shapes; ``QUEUE`` nodes use a real RabbitMQ connection.

**A note on the ``APPROVAL`` node test**: this suite deliberately never
runs :meth:`~app.services.approval.WorkflowApprovalService
.wait_for_decision` concurrently with a second coroutine deciding the
same approval over the same ``db_session`` -- ``AsyncSession`` is not
safe for genuinely concurrent use by two asyncio tasks, and a real
network round trip inside one task's own ``await`` is exactly where the
event loop is free to schedule the other task's own session call,
risking protocol-level corruption. The approval path is instead
exercised two ways that are each safe and still real: a full DAG run
that lets a very short ``timeout_seconds`` genuinely expire
(``test_approval_node_times_out_and_fails_workflow``), and
``tests/test_service_approval.py``'s own direct, sequential
decide-then-wait test (decide first, so ``wait_for_decision``'s first
poll iteration already finds it resolved and returns immediately,
never actually sleeping).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.events.base import DomainEvent
from shared_core.queue.factory import QueueFramework
from shared_core.workflow import WorkflowTaskQueue
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    CompensationStatus,
    NodeExecutionStatus,
    WorkflowInstanceStatus,
)
from app.repositories.workflow_checkpoint import WorkflowCheckpointRepository
from app.repositories.workflow_compensation import WorkflowCompensationRepository
from app.repositories.workflow_execution_step import WorkflowExecutionStepRepository
from app.repositories.workflow_instance import WorkflowInstanceRepository
from app.repositories.workflow_result import WorkflowResultRepository
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


def _task_node(node_id: str, job_id: str, *, retryable: bool = True) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "node_type": "task",
        "name": node_id,
        "config": {"job_id": job_id},
        "retryable": retryable,
    }


def _mock_job_execution(httpx_mock: HTTPXMock, job_id: str, *, final_status: str) -> None:
    execution_id = str(uuid.uuid4())
    httpx_mock.add_response(
        url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/jobs/{job_id}/execute",
        method="POST",
        status_code=201,
        json={"data": {"id": execution_id, "status": "pending"}},
    )
    httpx_mock.add_response(
        url=f"{AUTOMATION_SERVICE_BASE_URL}/automation/executions/{execution_id}",
        json={"data": {"id": execution_id, "status": final_status, "error_message": "boom"}},
    )


class TestHappyPath:
    async def test_linear_task_workflow_completes(
        self,
        db_session: AsyncSession,
        http_client: httpx.AsyncClient,
        httpx_mock: HTTPXMock,
        real_queue_framework: QueueFramework,
    ) -> None:
        job_id = str(uuid.uuid4())
        nodes: list[dict[str, Any]] = [
            {"node_id": "start", "node_type": "start", "name": "start"},
            _task_node("task", job_id),
            {"node_id": "end", "node_type": "end", "name": "end"},
        ]
        edges = [
            {"from_node_id": "start", "to_node_id": "task"},
            {"from_node_id": "task", "to_node_id": "end"},
        ]
        _mock_job_execution(httpx_mock, job_id, final_status="completed")

        definition = await make_definition(db_session)
        version = await make_version(db_session, definition, nodes=nodes, edges=edges)
        instance = await make_instance(db_session, definition, version)

        task_queue = WorkflowTaskQueue(real_queue_framework.manager)
        await task_queue.declare()
        service = build_execution_service(
            db_session, http_client=http_client, task_queue=task_queue
        )

        finished = await service.run_instance(instance.id, caller_token="tok")

        assert finished.status == WorkflowInstanceStatus.COMPLETED
        assert finished.started_at is not None
        assert finished.finished_at is not None

        steps = await WorkflowExecutionStepRepository(db_session).list_for_instance(instance.id)
        assert {step.node_id for step in steps} == {"start", "task", "end"}
        assert all(step.status == NodeExecutionStatus.COMPLETED for step in steps)

        result = await WorkflowResultRepository(db_session).get_for_instance(instance.id)
        assert result is not None
        assert result.success is True

        checkpoints = await WorkflowCheckpointRepository(db_session).list_for_instance(instance.id)
        assert len(checkpoints) >= 1


class TestFailureAndRollback:
    async def test_task_failure_marks_instance_failed(
        self,
        db_session: AsyncSession,
        http_client: httpx.AsyncClient,
        httpx_mock: HTTPXMock,
        real_queue_framework: QueueFramework,
    ) -> None:
        job_id = str(uuid.uuid4())
        nodes: list[dict[str, Any]] = [
            {"node_id": "start", "node_type": "start", "name": "start"},
            _task_node("task", job_id, retryable=False),
            {"node_id": "end", "node_type": "end", "name": "end"},
        ]
        edges = [
            {"from_node_id": "start", "to_node_id": "task"},
            {"from_node_id": "task", "to_node_id": "end"},
        ]
        _mock_job_execution(httpx_mock, job_id, final_status="failed")

        definition = await make_definition(db_session)
        version = await make_version(db_session, definition, nodes=nodes, edges=edges)
        instance = await make_instance(db_session, definition, version)

        task_queue = WorkflowTaskQueue(real_queue_framework.manager)
        await task_queue.declare()
        service = build_execution_service(
            db_session, http_client=http_client, task_queue=task_queue
        )

        finished = await service.run_instance(instance.id, caller_token="tok")

        assert finished.status == WorkflowInstanceStatus.FAILED
        assert finished.error_message is not None

    async def test_automatic_rollback_compensates_completed_node(
        self,
        db_session: AsyncSession,
        http_client: httpx.AsyncClient,
        httpx_mock: HTTPXMock,
        real_queue_framework: QueueFramework,
    ) -> None:
        job_1, job_2 = str(uuid.uuid4()), str(uuid.uuid4())
        nodes: list[dict[str, Any]] = [
            {"node_id": "start", "node_type": "start", "name": "start"},
            _task_node("task1", job_1, retryable=False),
            _task_node("task2", job_2, retryable=False),
            {"node_id": "end", "node_type": "end", "name": "end"},
        ]
        edges = [
            {"from_node_id": "start", "to_node_id": "task1"},
            {"from_node_id": "task1", "to_node_id": "task2"},
            {"from_node_id": "task2", "to_node_id": "end"},
        ]
        _mock_job_execution(httpx_mock, job_1, final_status="completed")
        _mock_job_execution(httpx_mock, job_2, final_status="failed")

        definition = await make_definition(db_session)
        version = await make_version(db_session, definition, nodes=nodes, edges=edges)
        instance = await make_instance(db_session, definition, version)

        task_queue = WorkflowTaskQueue(real_queue_framework.manager)
        await task_queue.declare()
        service = build_execution_service(
            db_session, http_client=http_client, task_queue=task_queue
        )

        finished = await service.run_instance(instance.id, caller_token="tok")

        assert finished.status == WorkflowInstanceStatus.ROLLED_BACK
        compensations = await WorkflowCompensationRepository(db_session).list_for_instance(
            instance.id
        )
        assert len(compensations) == 1
        assert compensations[0].node_id == "task1"
        assert compensations[0].status == CompensationStatus.COMPLETED


class TestApprovalTimeout:
    async def test_approval_node_times_out_and_fails_workflow(
        self,
        db_session: AsyncSession,
        http_client: httpx.AsyncClient,
        real_queue_framework: QueueFramework,
    ) -> None:
        nodes: list[dict[str, Any]] = [
            {"node_id": "start", "node_type": "start", "name": "start"},
            {
                "node_id": "approval",
                "node_type": "approval",
                "name": "approval",
                "config": {"approvers": ["alice"], "timeout_seconds": 0.05},
                "retryable": False,
            },
            {"node_id": "end", "node_type": "end", "name": "end"},
        ]
        edges = [
            {"from_node_id": "start", "to_node_id": "approval"},
            {"from_node_id": "approval", "to_node_id": "end"},
        ]
        definition = await make_definition(db_session)
        version = await make_version(db_session, definition, nodes=nodes, edges=edges)
        instance = await make_instance(db_session, definition, version)

        task_queue = WorkflowTaskQueue(real_queue_framework.manager)
        await task_queue.declare()
        service = build_execution_service(
            db_session,
            http_client=http_client,
            task_queue=task_queue,
            approval_poll_interval_seconds=0.02,
        )

        finished = await service.run_instance(instance.id, caller_token="tok")

        assert finished.status == WorkflowInstanceStatus.FAILED
        assert finished.error_message is not None
        assert "timed out" in finished.error_message


class TestWebhookNode:
    async def test_webhook_node_dispatches_real_http_call(
        self,
        db_session: AsyncSession,
        http_client: httpx.AsyncClient,
        httpx_mock: HTTPXMock,
        real_queue_framework: QueueFramework,
    ) -> None:
        nodes: list[dict[str, Any]] = [
            {"node_id": "start", "node_type": "start", "name": "start"},
            {
                "node_id": "hook",
                "node_type": "webhook",
                "name": "hook",
                "config": {"url": "http://hooks.internal/notify"},
            },
            {"node_id": "end", "node_type": "end", "name": "end"},
        ]
        edges = [
            {"from_node_id": "start", "to_node_id": "hook"},
            {"from_node_id": "hook", "to_node_id": "end"},
        ]
        httpx_mock.add_response(
            url="http://hooks.internal/notify", method="POST", json={"ok": True}
        )

        definition = await make_definition(db_session)
        version = await make_version(db_session, definition, nodes=nodes, edges=edges)
        instance = await make_instance(db_session, definition, version)

        task_queue = WorkflowTaskQueue(real_queue_framework.manager)
        await task_queue.declare()
        service = build_execution_service(
            db_session, http_client=http_client, task_queue=task_queue
        )

        finished = await service.run_instance(instance.id, caller_token="tok")

        assert finished.status == WorkflowInstanceStatus.COMPLETED


class TestQueueNode:
    async def test_queue_node_enqueues_via_real_rabbitmq(
        self,
        db_session: AsyncSession,
        http_client: httpx.AsyncClient,
        real_queue_framework: QueueFramework,
    ) -> None:
        nodes: list[dict[str, Any]] = [
            {"node_id": "start", "node_type": "start", "name": "start"},
            {
                "node_id": "enqueue",
                "node_type": "queue",
                "name": "enqueue",
                "config": {"payload": {"hello": "world"}},
            },
            {"node_id": "end", "node_type": "end", "name": "end"},
        ]
        edges = [
            {"from_node_id": "start", "to_node_id": "enqueue"},
            {"from_node_id": "enqueue", "to_node_id": "end"},
        ]
        definition = await make_definition(db_session)
        version = await make_version(db_session, definition, nodes=nodes, edges=edges)
        instance = await make_instance(db_session, definition, version)

        task_queue = WorkflowTaskQueue(real_queue_framework.manager)
        await task_queue.declare()
        service = build_execution_service(
            db_session, http_client=http_client, task_queue=task_queue
        )

        finished = await service.run_instance(instance.id, caller_token="tok")

        assert finished.status == WorkflowInstanceStatus.COMPLETED
        steps = await WorkflowExecutionStepRepository(db_session).list_for_instance(instance.id)
        enqueue_step = next(step for step in steps if step.node_id == "enqueue")
        assert enqueue_step.output == {"enqueued": True}


class TestEventNode:
    async def test_event_node_publishes_domain_event(
        self,
        db_session: AsyncSession,
        http_client: httpx.AsyncClient,
        real_queue_framework: QueueFramework,
    ) -> None:
        nodes: list[dict[str, Any]] = [
            {"node_id": "start", "node_type": "start", "name": "start"},
            {
                "node_id": "notify",
                "node_type": "event",
                "name": "notify",
                "config": {"payload": {"reason": "test"}},
            },
            {"node_id": "end", "node_type": "end", "name": "end"},
        ]
        edges = [
            {"from_node_id": "start", "to_node_id": "notify"},
            {"from_node_id": "notify", "to_node_id": "end"},
        ]
        definition = await make_definition(db_session)
        version = await make_version(db_session, definition, nodes=nodes, edges=edges)
        instance = await make_instance(db_session, definition, version)

        published: list[DomainEvent] = []

        async def _collect(event: DomainEvent) -> None:
            published.append(event)

        task_queue = WorkflowTaskQueue(real_queue_framework.manager)
        await task_queue.declare()
        service = build_execution_service(
            db_session, http_client=http_client, task_queue=task_queue, publish_event=_collect
        )

        finished = await service.run_instance(instance.id, caller_token="tok")

        assert finished.status == WorkflowInstanceStatus.COMPLETED
        custom_events = [event for event in published if event.event_name == "WorkflowCustomEvent"]
        assert len(custom_events) == 1
        assert custom_events[0].payload["reason"] == "test"


class TestSubWorkflowNode:
    async def test_sub_workflow_node_creates_and_runs_child_instance(
        self,
        db_session: AsyncSession,
        http_client: httpx.AsyncClient,
        httpx_mock: HTTPXMock,
        real_queue_framework: QueueFramework,
    ) -> None:
        child_job_id = str(uuid.uuid4())
        child_nodes: list[dict[str, Any]] = [
            {"node_id": "start", "node_type": "start", "name": "start"},
            _task_node("task", child_job_id),
            {"node_id": "end", "node_type": "end", "name": "end"},
        ]
        child_edges = [
            {"from_node_id": "start", "to_node_id": "task"},
            {"from_node_id": "task", "to_node_id": "end"},
        ]
        _mock_job_execution(httpx_mock, child_job_id, final_status="completed")

        child_definition = await make_definition(db_session, workflow_key="child-workflow")
        await make_version(db_session, child_definition, nodes=child_nodes, edges=child_edges)

        parent_nodes: list[dict[str, Any]] = [
            {"node_id": "start", "node_type": "start", "name": "start"},
            {
                "node_id": "sub",
                "node_type": "sub_workflow",
                "name": "sub",
                "config": {"workflow_key": "child-workflow"},
            },
            {"node_id": "end", "node_type": "end", "name": "end"},
        ]
        parent_edges = [
            {"from_node_id": "start", "to_node_id": "sub"},
            {"from_node_id": "sub", "to_node_id": "end"},
        ]
        parent_definition = await make_definition(
            db_session,
            organization_id=child_definition.organization_id,
            workflow_key="parent-workflow",
        )
        parent_version = await make_version(
            db_session, parent_definition, nodes=parent_nodes, edges=parent_edges
        )
        parent_instance = await make_instance(db_session, parent_definition, parent_version)

        task_queue = WorkflowTaskQueue(real_queue_framework.manager)
        await task_queue.declare()
        service = build_execution_service(
            db_session, http_client=http_client, task_queue=task_queue
        )

        finished = await service.run_instance(parent_instance.id, caller_token="tok")

        assert finished.status == WorkflowInstanceStatus.COMPLETED
        children = await WorkflowInstanceRepository(db_session).list_children(parent_instance.id)
        assert len(children) == 1
        assert children[0].status == WorkflowInstanceStatus.COMPLETED
        assert children[0].parent_instance_id == parent_instance.id
