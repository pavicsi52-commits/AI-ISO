"""Tests for :mod:`app.workflow.handlers`."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from shared_core.workflow.context import WorkflowContext
from shared_core.workflow.exceptions import TaskExecutionError
from shared_core.workflow.nodes import NodeDefinition, NodeType

from app.workflow.handlers import build_automation_task_handler


class TestBuildAutomationTaskHandler:
    async def test_calls_execute_job_and_wait_with_job_id(self) -> None:
        job_id = uuid.uuid4()
        calls: list[dict[str, Any]] = []

        async def _fake_execute(job_id_arg: uuid.UUID, **kwargs: Any) -> dict[str, Any]:
            calls.append({"job_id": job_id_arg, **kwargs})
            return {"status": "completed"}

        handler = build_automation_task_handler(_fake_execute)
        node = NodeDefinition(
            node_id="n1", node_type=NodeType.TASK, name="run-job", config={"job_id": str(job_id)}
        )
        context = WorkflowContext(workflow_id="wf1", user_id=str(uuid.uuid4()))

        result = await handler(node, context)

        assert result == {"status": "completed"}
        assert calls[0]["job_id"] == job_id
        assert calls[0]["triggered_by"] is not None

    async def test_merges_node_config_and_context_variables(self) -> None:
        job_id = uuid.uuid4()
        captured: dict[str, Any] = {}

        async def _fake_execute(_job_id: uuid.UUID, **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {}

        handler = build_automation_task_handler(_fake_execute)
        node = NodeDefinition(
            node_id="n1",
            node_type=NodeType.TASK,
            name="run-job",
            config={"job_id": str(job_id), "variables": {"env": "prod"}},
        )
        context = WorkflowContext(workflow_id="wf1")
        context.variables.set("region", "us-east-1")

        await handler(node, context)

        assert captured["variables"]["env"] == "prod"
        assert captured["variables"]["region"] == "us-east-1"

    async def test_no_user_id_means_no_triggered_by(self) -> None:
        job_id = uuid.uuid4()
        captured: dict[str, Any] = {}

        async def _fake_execute(_job_id: uuid.UUID, **kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {}

        handler = build_automation_task_handler(_fake_execute)
        node = NodeDefinition(
            node_id="n1", node_type=NodeType.TASK, name="run-job", config={"job_id": str(job_id)}
        )
        context = WorkflowContext(workflow_id="wf1", user_id=None)

        await handler(node, context)

        assert captured["triggered_by"] is None

    async def test_missing_job_id_raises_task_execution_error(self) -> None:
        async def _fake_execute(_job_id: uuid.UUID, **_kwargs: Any) -> dict[str, Any]:
            return {}

        handler = build_automation_task_handler(_fake_execute)
        node = NodeDefinition(node_id="n1", node_type=NodeType.TASK, name="run-job", config={})
        context = WorkflowContext(workflow_id="wf1")

        with pytest.raises(TaskExecutionError, match="no 'job_id'"):
            await handler(node, context)
