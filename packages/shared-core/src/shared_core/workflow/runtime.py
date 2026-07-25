"""Workflow runtime.

Per docs/028_Enterprise_Workflow_SDK.md.txt "ACCEPTANCE CRITERIA":
Runtime; "PERFORMANCE": Async Execution, Persistent Runtime. Tracks
every workflow execution this process has started as a background
:class:`asyncio.Task`, so a caller can start many executions without
blocking and later inspect, wait on, or cancel any of them by id.
Purely in-process, the same "no business tables" stance as every prior
framework's own state; "Persistent Runtime" in a running service is
whatever repository layer wraps this.
"""

from __future__ import annotations

import asyncio

from shared_core.workflow.compiler import CompiledWorkflow
from shared_core.workflow.context import WorkflowContext
from shared_core.workflow.engine import WorkflowEngine
from shared_core.workflow.exceptions import WorkflowNotFoundError
from shared_core.workflow.execution import WorkflowExecution


class WorkflowRuntime:
    """Tracks every workflow execution this process is running or has run."""

    def __init__(self, engine: WorkflowEngine) -> None:
        self._engine = engine
        self._tasks: dict[str, asyncio.Task[WorkflowExecution]] = {}

    async def start(self, compiled: CompiledWorkflow, context: WorkflowContext) -> str:
        """Start running *compiled* in the background, returning its execution id.

        "Async Execution": doesn't await the run itself; use :meth:`wait`
        to retrieve the final :class:`~shared_core.workflow.execution.WorkflowExecution`.
        """
        execution_id = context.execution_id
        self._tasks[execution_id] = asyncio.create_task(self._engine.run(compiled, context))
        return execution_id

    async def wait(self, execution_id: str) -> WorkflowExecution:
        """Wait for *execution_id* to finish and return its final state.

        Raises:
            WorkflowNotFoundError: If *execution_id* was never started.
        """
        return await self._get_task(execution_id)

    def is_running(self, execution_id: str) -> bool:
        """Whether *execution_id* is still in progress.

        Raises:
            WorkflowNotFoundError: If *execution_id* was never started.
        """
        return not self._get_task(execution_id).done()

    def cancel(self, execution_id: str) -> None:
        """Cancel a running execution.

        Raises:
            WorkflowNotFoundError: If *execution_id* was never started.
        """
        self._get_task(execution_id).cancel()

    def list_execution_ids(self) -> list[str]:
        """Every execution id this runtime is tracking."""
        return list(self._tasks)

    def discard(self, execution_id: str) -> None:
        """Stop tracking *execution_id*. A no-op if it isn't tracked."""
        self._tasks.pop(execution_id, None)

    def _get_task(self, execution_id: str) -> asyncio.Task[WorkflowExecution]:
        try:
            return self._tasks[execution_id]
        except KeyError as exc:
            raise WorkflowNotFoundError(f"No execution tracked with id {execution_id!r}.") from exc


__all__ = ["WorkflowRuntime"]
