"""Workflow execution engine.

Per docs/028_Enterprise_Workflow_SDK.md.txt "ACCEPTANCE CRITERIA":
Workflow Engine. Runs a
:class:`~shared_core.workflow.compiler.CompiledWorkflow` from ``START``
to ``END`` (or until failure/cancellation), level by level per its
precomputed execution plan -- nodes within one level run concurrently
via :func:`shared_core.workflow.parallel.run_parallel` (the same
mechanism that makes ``PARALLEL``/``MERGE`` node types "just work":
independent branches are already grouped into the same level).
Integrates checkpointing, rollback, retry, telemetry, metrics, audit,
and events at the one place every workflow execution actually runs
through.

A node failure never raises out of :meth:`WorkflowEngine.run` -- it's
recorded in the returned execution's own state (``status == FAILED``,
``node_results`` showing which node failed and why), the same
"traceable, not exceptional" contract as
:meth:`shared_core.scheduler.executor.JobExecutor.execute`.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager, nullcontext
from datetime import UTC, datetime
from typing import Any

from opentelemetry.trace import Tracer

from shared_core.queue.retry import RetryPolicy
from shared_core.workflow import audit as workflow_audit
from shared_core.workflow import metrics as workflow_metrics
from shared_core.workflow.checkpoint import Checkpoint, CheckpointStore
from shared_core.workflow.compensation import CompensationRegistry
from shared_core.workflow.compiler import CompiledWorkflow
from shared_core.workflow.conditions import evaluate_if_else
from shared_core.workflow.constants import DEFAULT_SOURCE_SERVICE
from shared_core.workflow.context import WorkflowContext
from shared_core.workflow.edges import EdgeDefinition
from shared_core.workflow.events import (
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskStartedEvent,
    WorkflowCompletedEvent,
    WorkflowEvent,
    WorkflowFailedEvent,
    WorkflowStartedEvent,
    build_workflow_event,
)
from shared_core.workflow.execution import NodeExecutionResult, WorkflowExecution
from shared_core.workflow.executor import NodeExecutor
from shared_core.workflow.graph import WorkflowGraph
from shared_core.workflow.nodes import NodeDefinition, NodeType
from shared_core.workflow.parallel import run_parallel
from shared_core.workflow.retry import workflow_retry_policy
from shared_core.workflow.rollback import rollback_workflow
from shared_core.workflow.state_machine import WorkflowState
from shared_core.workflow.telemetry import trace_workflow_execution, trace_workflow_step
from shared_core.workflow.variables import VariableScope

EventHandler = Callable[[WorkflowEvent], Awaitable[None]]


class WorkflowEngine:
    """Runs a compiled workflow to completion."""

    def __init__(
        self,
        executor: NodeExecutor,
        *,
        compensations: CompensationRegistry | None = None,
        checkpoints: CheckpointStore | None = None,
        tracer: Tracer | None = None,
        on_event: EventHandler | None = None,
        source_service: str = DEFAULT_SOURCE_SERVICE,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self._executor = executor
        self._compensations = compensations if compensations is not None else CompensationRegistry()
        self._checkpoints = checkpoints if checkpoints is not None else CheckpointStore()
        self._tracer = tracer
        self._on_event = on_event
        self._source_service = source_service
        self._retry_policy = retry_policy if retry_policy is not None else workflow_retry_policy()

    async def run(self, compiled: CompiledWorkflow, context: WorkflowContext) -> WorkflowExecution:
        """Run *compiled* to completion or failure, always returning its final execution state."""
        definition = compiled.definition
        execution = WorkflowExecution(
            execution_id=context.execution_id,
            workflow_id=definition.workflow_id,
            workflow_version=definition.version,
        )
        for name, value in definition.default_variables.items():
            context.variables.set(name, value, scope=VariableScope.WORKFLOW)

        execution.state_machine.transition(WorkflowState.PENDING)
        execution.state_machine.transition(WorkflowState.RUNNING)
        workflow_metrics.record_execution_started(definition.workflow_id)
        workflow_audit.audit_execution_started(execution.execution_id, definition.workflow_id)
        await self._emit(WorkflowStartedEvent, execution, definition.workflow_id)

        start = time.perf_counter()
        try:
            with self._trace_execution(definition.workflow_id):
                await self._run_plan(compiled, execution, context)
        except Exception as exc:
            await self._finish_failed(execution, definition.workflow_id, start, exc, context)
            return execution

        duration = time.perf_counter() - start
        execution.state_machine.transition(WorkflowState.COMPLETED)
        execution.finished_at = datetime.now(UTC)
        workflow_metrics.record_success(definition.workflow_id, duration_seconds=duration)
        workflow_audit.audit_execution_completed(execution.execution_id, definition.workflow_id)
        await self._emit(WorkflowCompletedEvent, execution, definition.workflow_id)
        return execution

    def _trace_execution(self, workflow_id: str) -> AbstractContextManager[object]:
        if self._tracer is None:
            return nullcontext()
        return trace_workflow_execution(self._tracer, workflow_id)

    async def _finish_failed(
        self,
        execution: WorkflowExecution,
        workflow_id: str,
        start: float,
        exc: Exception,
        context: WorkflowContext,
    ) -> None:
        duration = time.perf_counter() - start
        execution.state_machine.transition(WorkflowState.FAILED)
        execution.finished_at = datetime.now(UTC)
        workflow_metrics.record_failure(workflow_id, duration_seconds=duration)
        workflow_audit.audit_execution_failed(execution.execution_id, workflow_id, error=str(exc))
        await self._emit(WorkflowFailedEvent, execution, workflow_id, error=str(exc))
        await self._rollback(execution, context)

    async def _run_plan(
        self, compiled: CompiledWorkflow, execution: WorkflowExecution, context: WorkflowContext
    ) -> None:
        graph = compiled.graph
        for level in compiled.execution_plan:
            ready = [
                node_id
                for node_id in level
                if self._is_node_ready(graph, node_id, execution, context)
            ]
            for node_id in set(level) - set(ready):
                execution.record_node_result(self._skipped_result(node_id))

            branches = {
                node_id: self._make_branch(node_id, graph, execution, context) for node_id in ready
            }
            results = await run_parallel(branches)
            for result in results:
                if not result.succeeded and result.error is not None:
                    raise result.error
            self._save_checkpoint(execution, context)

    def _make_branch(
        self,
        node_id: str,
        graph: WorkflowGraph,
        execution: WorkflowExecution,
        context: WorkflowContext,
    ) -> Callable[[], Awaitable[None]]:
        async def _branch() -> None:
            await self._run_node(node_id, graph, execution, context)

        return _branch

    async def _run_node(
        self,
        node_id: str,
        graph: WorkflowGraph,
        execution: WorkflowExecution,
        context: WorkflowContext,
    ) -> None:
        node = graph.get_node(node_id)
        node_context = context.child(node_id=node_id)
        started_at = datetime.now(UTC)
        await self._emit(TaskStartedEvent, execution, execution.workflow_id, node_id=node_id)

        policy = self._retry_policy
        max_attempts = policy.max_attempts if node.retryable else 1
        last_error: Exception | None = None
        attempts = 0
        for attempt in range(1, max_attempts + 1):
            attempts = attempt
            try:
                output = await self._run_node_once(node, node_context, execution.workflow_id)
            except Exception as exc:
                last_error = exc
                is_final = attempt == max_attempts
                if not node.retryable or not policy.classify(exc) or is_final:
                    break
                workflow_metrics.record_retry(execution.workflow_id)
                await asyncio.sleep(policy.delay_for(attempt))
                continue
            execution.record_node_result(
                NodeExecutionResult(
                    node_id=node_id,
                    status=WorkflowState.COMPLETED,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                    output=output,
                    attempts=attempts,
                )
            )
            await self._emit(TaskCompletedEvent, execution, execution.workflow_id, node_id=node_id)
            return

        execution.record_node_result(
            NodeExecutionResult(
                node_id=node_id,
                status=WorkflowState.FAILED,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                error=str(last_error),
                attempts=attempts,
            )
        )
        await self._emit(
            TaskFailedEvent,
            execution,
            execution.workflow_id,
            node_id=node_id,
            error=str(last_error),
        )
        assert last_error is not None  # the loop only exits early after setting it
        raise last_error

    async def _run_node_once(
        self, node: NodeDefinition, node_context: WorkflowContext, workflow_id: str
    ) -> Any:
        step_context = self._trace_step(workflow_id, node.name)
        with step_context, workflow_metrics.measure_task(workflow_id, node.node_type.value):
            return await self._executor.execute(node, node_context)

    def _trace_step(self, workflow_id: str, step_name: str) -> AbstractContextManager[object]:
        if self._tracer is None:
            return nullcontext()
        return trace_workflow_step(self._tracer, workflow_id, step_name)

    def _is_node_ready(
        self,
        graph: WorkflowGraph,
        node_id: str,
        execution: WorkflowExecution,
        context: WorkflowContext,
    ) -> bool:
        node = graph.get_node(node_id)
        predecessors = graph.predecessors(node_id)
        if not predecessors:
            return True
        variables = context.variables.as_dict(include_secrets=True)
        satisfied = [self._edge_satisfied(edge, execution, variables) for edge in predecessors]
        if node.node_type == NodeType.MERGE:
            return all(satisfied)
        return any(satisfied)

    @staticmethod
    def _edge_satisfied(
        edge: EdgeDefinition, execution: WorkflowExecution, variables: dict[str, Any]
    ) -> bool:
        predecessor_result = execution.node_results.get(edge.from_node_id)
        completed = (
            predecessor_result is not None and predecessor_result.status == WorkflowState.COMPLETED
        )
        if not completed:
            return False
        return edge.condition is None or evaluate_if_else(edge.condition, variables)

    def _skipped_result(self, node_id: str) -> NodeExecutionResult:
        now = datetime.now(UTC)
        return NodeExecutionResult(
            node_id=node_id, status=WorkflowState.CANCELLED, started_at=now, finished_at=now
        )

    def _save_checkpoint(self, execution: WorkflowExecution, context: WorkflowContext) -> None:
        self._checkpoints.save(
            Checkpoint(
                execution_id=execution.execution_id,
                state=execution.status,
                completed_node_ids=tuple(execution.completed_node_ids()),
                variables_snapshot=context.variables.as_dict(include_secrets=True),
            )
        )

    async def _rollback(self, execution: WorkflowExecution, context: WorkflowContext) -> None:
        try:
            compensated = await rollback_workflow(execution, self._compensations, context)
        except Exception:
            return
        if compensated:
            execution.state_machine.transition(WorkflowState.ROLLED_BACK)
            workflow_metrics.record_rollback(execution.workflow_id)
            workflow_audit.audit_rollback_executed(
                execution.execution_id, execution.workflow_id, node_ids=compensated
            )

    async def _emit(
        self,
        event_cls: type[WorkflowEvent],
        execution: WorkflowExecution,
        workflow_id: str,
        *,
        node_id: str | None = None,
        **extra: object,
    ) -> None:
        if self._on_event is None:
            return
        event = build_workflow_event(
            event_cls,
            source_service=self._source_service,
            execution_id=execution.execution_id,
            workflow_id=workflow_id,
            node_id=node_id,
            **extra,
        )
        await self._on_event(event)


__all__ = ["EventHandler", "WorkflowEngine"]
