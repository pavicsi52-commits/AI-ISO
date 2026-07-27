"""Direct unit tests for the node handlers under :mod:`app.handlers`.

Each handler accepts an injected collaborator (``trigger``, an
``httpx.AsyncClient``, an :class:`~app.clients.automation_client
.AutomationClient`), so these are tested in isolation with fake
``NodeDefinition``/``WorkflowContext`` pairs rather than through a full
DAG run -- the full-DAG happy paths are already covered end to end in
``test_service_execution.py``; this file closes the handlers' own
error-path and ``LOOP``-node coverage gaps.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pytest_httpx import HTTPXMock
from shared_core.workflow import (
    MaxIterationsExceededError,
    NodeDefinition,
    NodeType,
    TaskExecutionError,
    WorkflowContext,
)

from app.handlers.subworkflow import build_loop_handler, build_subworkflow_handler
from app.handlers.task import build_task_and_connector_handler
from app.handlers.webhook import build_webhook_handler


def _node(node_type: NodeType, config: dict[str, Any]) -> NodeDefinition:
    return NodeDefinition(node_id="n1", node_type=node_type, name="n1", config=config)


def _context() -> WorkflowContext:
    return WorkflowContext(workflow_id="wf-1")


class TestSubWorkflowHandler:
    async def test_missing_workflow_key_raises(self) -> None:
        handler = build_subworkflow_handler(trigger=None)  # type: ignore[arg-type]
        with pytest.raises(TaskExecutionError, match="workflow_key"):
            await handler(_node(NodeType.SUB_WORKFLOW, {}), _context())


class TestLoopHandler:
    async def test_runs_trigger_once_per_item_and_collects_results(self) -> None:
        seen_variables: list[dict[str, Any]] = []

        async def trigger(
            workflow_key: str, version: str | None, variables: dict[str, Any]
        ) -> dict[str, Any]:
            seen_variables.append(dict(variables))
            return {"workflow_key": workflow_key, "item": variables["item"]}

        handler = build_loop_handler(trigger, max_iterations=10)
        node = _node(
            NodeType.LOOP,
            {"workflow_key": "process-item", "items": ["a", "b", "c"]},
        )

        results = await handler(node, _context())

        assert results == [
            {"workflow_key": "process-item", "item": "a"},
            {"workflow_key": "process-item", "item": "b"},
            {"workflow_key": "process-item", "item": "c"},
        ]
        assert [v["item"] for v in seen_variables] == ["a", "b", "c"]

    async def test_missing_workflow_key_raises(self) -> None:
        async def trigger(
            workflow_key: str, version: str | None, variables: dict[str, Any]
        ) -> dict[str, Any]:
            raise AssertionError("must not be called")

        handler = build_loop_handler(trigger, max_iterations=10)
        with pytest.raises(TaskExecutionError, match="workflow_key"):
            await handler(_node(NodeType.LOOP, {"items": [1]}), _context())

    async def test_exceeding_max_iterations_raises(self) -> None:
        async def trigger(
            workflow_key: str, version: str | None, variables: dict[str, Any]
        ) -> dict[str, Any]:
            raise AssertionError("must not be called")

        handler = build_loop_handler(trigger, max_iterations=2)
        node = _node(NodeType.LOOP, {"workflow_key": "wf", "items": [1, 2, 3]})

        with pytest.raises(MaxIterationsExceededError):
            await handler(node, _context())

    async def test_custom_item_variable_name(self) -> None:
        captured: dict[str, Any] = {}

        async def trigger(
            workflow_key: str, version: str | None, variables: dict[str, Any]
        ) -> dict[str, Any]:
            captured.update(variables)
            return {}

        handler = build_loop_handler(trigger, max_iterations=10)
        node = _node(
            NodeType.LOOP,
            {"workflow_key": "wf", "items": ["x"], "item_variable": "target"},
        )

        await handler(node, _context())

        assert captured["target"] == "x"


class TestTaskHandler:
    async def test_missing_job_id_raises(self) -> None:
        handler = build_task_and_connector_handler(client=None)  # type: ignore[arg-type]
        with pytest.raises(TaskExecutionError, match="job_id"):
            await handler(_node(NodeType.TASK, {}), _context())


class TestWebhookHandler:
    async def test_missing_url_raises(self) -> None:
        async with httpx.AsyncClient() as client:
            handler = build_webhook_handler(client)
            with pytest.raises(TaskExecutionError, match="url"):
                await handler(_node(NodeType.WEBHOOK, {}), _context())

    async def test_request_failure_raises_task_execution_error(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_exception(httpx.ConnectError("connection refused"))
        async with httpx.AsyncClient() as client:
            handler = build_webhook_handler(client)
            node = _node(NodeType.WEBHOOK, {"url": "https://example.invalid/hook"})
            with pytest.raises(TaskExecutionError, match="request failed"):
                await handler(node, _context())


__all__: list[str] = []
