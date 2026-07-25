"""Workflow node handlers this service registers into ``shared_core
.workflow``'s own ``NodeHandlerRegistry``, per docs/040 "WORKFLOW
INTEGRATION" "Workflow Task Execution"/"Workflow Callbacks"/"Execution
Context"/"Shared Variables". A ``TASK``/``CONNECTOR`` node whose own
``config`` names a ``job_id`` triggers that automation job's execution
and blocks until it reaches a terminal state, returning the
execution's own outputs as the node's result so downstream workflow
nodes can consume them ("Shared Variables").
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from shared_core.workflow.context import WorkflowContext
from shared_core.workflow.exceptions import TaskExecutionError
from shared_core.workflow.nodes import NodeDefinition

ExecuteJobAndWait = Callable[..., Awaitable[dict[str, Any]]]
TaskNodeHandler = Callable[[NodeDefinition, WorkflowContext], Awaitable[dict[str, Any]]]


def build_automation_task_handler(execute_job_and_wait: ExecuteJobAndWait) -> TaskNodeHandler:
    """Build the ``TASK``/``CONNECTOR`` node handler this service
    registers, closing over *execute_job_and_wait* (this service's own
    execution-service method, bound to a request-scoped database
    session by whichever code wires the workflow engine up).
    """

    async def handle_task_node(node: NodeDefinition, context: WorkflowContext) -> dict[str, Any]:
        job_id_raw = node.config.get("job_id")
        if job_id_raw is None:
            raise TaskExecutionError(
                f"Workflow node {node.node_id!r} has no 'job_id' in its own config."
            )
        variables: dict[str, Any] = dict(node.config.get("variables", {}))
        variables.update(context.variables.as_dict(include_secrets=True))
        return await execute_job_and_wait(
            UUID(str(job_id_raw)),
            variables=variables,
            triggered_by=UUID(context.user_id) if context.user_id else None,
        )

    return handle_task_node


__all__ = ["ExecuteJobAndWait", "TaskNodeHandler", "build_automation_task_handler"]
