"""Tests for engine.py and runtime.py."""

from __future__ import annotations

import asyncio

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from shared_core.queue.retry import RetryPolicy
from shared_core.workflow.checkpoint import CheckpointStore
from shared_core.workflow.compensation import CompensationRegistry
from shared_core.workflow.compiler import compile_workflow
from shared_core.workflow.context import WorkflowContext
from shared_core.workflow.definition import WorkflowDefinition
from shared_core.workflow.edges import EdgeDefinition
from shared_core.workflow.engine import WorkflowEngine
from shared_core.workflow.events import WorkflowEvent
from shared_core.workflow.exceptions import WorkflowNotFoundError
from shared_core.workflow.executor import NodeExecutor, NodeHandlerRegistry
from shared_core.workflow.nodes import NodeDefinition, NodeType
from shared_core.workflow.parser import WorkflowBuilder
from shared_core.workflow.runtime import WorkflowRuntime
from shared_core.workflow.state_machine import WorkflowState
from shared_core.workflow.variables import VariableScope


def _provider() -> tuple[TracerProvider, InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


def _linear_definition() -> WorkflowDefinition:
    return (
        WorkflowBuilder("wf-1", "Sample")
        .node(NodeDefinition(node_id="start", node_type=NodeType.START, name="start"))
        .node(NodeDefinition(node_id="task", node_type=NodeType.TASK, name="task"))
        .node(NodeDefinition(node_id="end", node_type=NodeType.END, name="end"))
        .edge(EdgeDefinition(from_node_id="start", to_node_id="task"))
        .edge(EdgeDefinition(from_node_id="task", to_node_id="end"))
        .build()
    )


_FAST_RETRY_POLICY = RetryPolicy(
    max_attempts=3, backoff_base_seconds=0.001, backoff_max_seconds=0.01
)


def _engine(handlers: NodeHandlerRegistry | None = None) -> WorkflowEngine:
    executor = NodeExecutor(handlers if handlers is not None else NodeHandlerRegistry())
    return WorkflowEngine(executor, retry_policy=_FAST_RETRY_POLICY)


# --- engine.py: happy path ---


async def test_engine_runs_a_linear_workflow_to_completion() -> None:
    handlers = NodeHandlerRegistry()

    async def task_handler(_node: NodeDefinition, _context: WorkflowContext) -> str:
        return "done"

    handlers.register(NodeType.TASK, task_handler)
    engine = _engine(handlers)
    compiled = compile_workflow(_linear_definition())
    context = WorkflowContext(workflow_id="wf-1")

    execution = await engine.run(compiled, context)

    assert execution.status == WorkflowState.COMPLETED
    assert execution.node_results["task"].status == WorkflowState.COMPLETED
    assert execution.node_results["task"].output == "done"
    assert execution.finished_at is not None


async def test_engine_records_failure_without_raising() -> None:
    engine = _engine()  # no handler registered for TASK
    compiled = compile_workflow(_linear_definition())
    context = WorkflowContext(workflow_id="wf-1")

    execution = await engine.run(compiled, context)

    assert execution.status == WorkflowState.FAILED
    assert execution.node_results["task"].status == WorkflowState.FAILED
    assert execution.node_results["task"].error is not None


# --- engine.py: conditional branching ---


def _branching_definition() -> WorkflowDefinition:
    return (
        WorkflowBuilder("wf-branch", "Branching")
        .node(NodeDefinition(node_id="start", node_type=NodeType.START, name="start"))
        .node(
            NodeDefinition(
                node_id="cond",
                node_type=NodeType.CONDITION,
                name="cond",
                config={"expression": "flag == True"},
            )
        )
        .node(NodeDefinition(node_id="true_branch", node_type=NodeType.TASK, name="true_branch"))
        .node(NodeDefinition(node_id="false_branch", node_type=NodeType.TASK, name="false_branch"))
        .node(NodeDefinition(node_id="end", node_type=NodeType.END, name="end"))
        .edge(EdgeDefinition(from_node_id="start", to_node_id="cond"))
        .edge(
            EdgeDefinition(from_node_id="cond", to_node_id="true_branch", condition="flag == True")
        )
        .edge(
            EdgeDefinition(
                from_node_id="cond", to_node_id="false_branch", condition="flag == False"
            )
        )
        .edge(EdgeDefinition(from_node_id="true_branch", to_node_id="end"))
        .edge(EdgeDefinition(from_node_id="false_branch", to_node_id="end"))
        .build()
    )


async def test_engine_only_runs_the_matching_branch() -> None:
    handlers = NodeHandlerRegistry()
    ran: list[str] = []

    async def handler(node: NodeDefinition, _context: WorkflowContext) -> None:
        ran.append(node.node_id)

    handlers.register(NodeType.TASK, handler)
    engine = _engine(handlers)
    compiled = compile_workflow(_branching_definition())
    context = WorkflowContext(workflow_id="wf-branch")
    context.variables.set("flag", True, scope=VariableScope.RUNTIME)

    execution = await engine.run(compiled, context)

    assert execution.status == WorkflowState.COMPLETED
    assert ran == ["true_branch"]
    assert execution.node_results["false_branch"].status == WorkflowState.CANCELLED


# --- engine.py: parallel/merge ---


def _parallel_definition() -> WorkflowDefinition:
    return (
        WorkflowBuilder("wf-parallel", "Parallel")
        .node(NodeDefinition(node_id="start", node_type=NodeType.START, name="start"))
        .node(NodeDefinition(node_id="branch_a", node_type=NodeType.TASK, name="branch_a"))
        .node(NodeDefinition(node_id="branch_b", node_type=NodeType.TASK, name="branch_b"))
        .node(NodeDefinition(node_id="merge", node_type=NodeType.MERGE, name="merge"))
        .node(NodeDefinition(node_id="end", node_type=NodeType.END, name="end"))
        .edge(EdgeDefinition(from_node_id="start", to_node_id="branch_a"))
        .edge(EdgeDefinition(from_node_id="start", to_node_id="branch_b"))
        .edge(EdgeDefinition(from_node_id="branch_a", to_node_id="merge"))
        .edge(EdgeDefinition(from_node_id="branch_b", to_node_id="merge"))
        .edge(EdgeDefinition(from_node_id="merge", to_node_id="end"))
        .build()
    )


async def test_engine_runs_independent_branches_and_waits_at_merge() -> None:
    handlers = NodeHandlerRegistry()
    ran: list[str] = []

    async def handler(node: NodeDefinition, _context: WorkflowContext) -> None:
        ran.append(node.node_id)

    handlers.register(NodeType.TASK, handler)
    engine = _engine(handlers)
    compiled = compile_workflow(_parallel_definition())
    context = WorkflowContext(workflow_id="wf-parallel")

    execution = await engine.run(compiled, context)

    assert execution.status == WorkflowState.COMPLETED
    assert set(ran) == {"branch_a", "branch_b"}
    assert execution.node_results["merge"].status == WorkflowState.COMPLETED


async def test_engine_merge_waits_for_all_predecessors() -> None:
    handlers = NodeHandlerRegistry()

    async def failing(_node: NodeDefinition, _context: WorkflowContext) -> None:
        raise RuntimeError("branch_a failed")

    async def succeeding(_node: NodeDefinition, _context: WorkflowContext) -> None:
        return None

    async def dispatch(node: NodeDefinition, context: WorkflowContext) -> None:
        if node.node_id == "branch_a":
            await failing(node, context)
        else:
            await succeeding(node, context)

    handlers.register(NodeType.TASK, dispatch)
    engine = _engine(handlers)
    compiled = compile_workflow(_parallel_definition())
    context = WorkflowContext(workflow_id="wf-parallel")

    execution = await engine.run(compiled, context)

    assert execution.status == WorkflowState.FAILED
    assert "merge" not in execution.node_results


# --- engine.py: retry ---


async def test_engine_retries_a_failing_node_and_eventually_succeeds() -> None:
    handlers = NodeHandlerRegistry()
    calls = 0

    async def flaky(_node: NodeDefinition, _context: WorkflowContext) -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise RuntimeError("transient")
        return "ok"

    handlers.register(NodeType.TASK, flaky)
    engine = _engine(handlers)
    compiled = compile_workflow(_linear_definition())
    context = WorkflowContext(workflow_id="wf-1")

    execution = await engine.run(compiled, context)

    assert execution.status == WorkflowState.COMPLETED
    assert execution.node_results["task"].attempts == 2


async def test_engine_does_not_retry_a_non_retryable_node() -> None:
    handlers = NodeHandlerRegistry()
    calls = 0

    async def always_fails(_node: NodeDefinition, _context: WorkflowContext) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("permanent")

    handlers.register(NodeType.TASK, always_fails)
    engine = _engine(handlers)
    definition = (
        WorkflowBuilder("wf-1", "Sample")
        .node(NodeDefinition(node_id="start", node_type=NodeType.START, name="start"))
        .node(NodeDefinition(node_id="task", node_type=NodeType.TASK, name="task", retryable=False))
        .node(NodeDefinition(node_id="end", node_type=NodeType.END, name="end"))
        .edge(EdgeDefinition(from_node_id="start", to_node_id="task"))
        .edge(EdgeDefinition(from_node_id="task", to_node_id="end"))
        .build()
    )
    context = WorkflowContext(workflow_id="wf-1")

    execution = await engine.run(compile_workflow(definition), context)

    assert execution.status == WorkflowState.FAILED
    assert calls == 1


# --- engine.py: rollback/compensation ---


async def test_engine_rolls_back_completed_nodes_when_a_later_node_fails() -> None:
    handlers = NodeHandlerRegistry()
    compensated: list[str] = []

    async def dispatch(node: NodeDefinition, _context: WorkflowContext) -> None:
        if node.node_id == "task2":
            raise RuntimeError("boom")

    handlers.register(NodeType.TASK, dispatch)
    compensations = CompensationRegistry()

    async def undo_task1(_context: WorkflowContext) -> None:
        compensated.append("task1")

    compensations.register("task1", undo_task1)

    definition = (
        WorkflowBuilder("wf-1", "Sample")
        .node(NodeDefinition(node_id="start", node_type=NodeType.START, name="start"))
        .node(
            NodeDefinition(node_id="task1", node_type=NodeType.TASK, name="task1", retryable=False)
        )
        .node(
            NodeDefinition(node_id="task2", node_type=NodeType.TASK, name="task2", retryable=False)
        )
        .node(NodeDefinition(node_id="end", node_type=NodeType.END, name="end"))
        .edge(EdgeDefinition(from_node_id="start", to_node_id="task1"))
        .edge(EdgeDefinition(from_node_id="task1", to_node_id="task2"))
        .edge(EdgeDefinition(from_node_id="task2", to_node_id="end"))
        .build()
    )
    executor = NodeExecutor(handlers)
    engine = WorkflowEngine(executor, compensations=compensations)
    context = WorkflowContext(workflow_id="wf-1")

    execution = await engine.run(compile_workflow(definition), context)

    assert execution.status == WorkflowState.ROLLED_BACK
    assert compensated == ["task1"]
    assert execution.node_results["task1"].status == WorkflowState.ROLLED_BACK


# --- engine.py: checkpoints ---


async def test_engine_saves_a_checkpoint_after_each_level() -> None:
    handlers = NodeHandlerRegistry()

    async def task_handler(_node: NodeDefinition, _context: WorkflowContext) -> str:
        return "done"

    handlers.register(NodeType.TASK, task_handler)
    checkpoints = CheckpointStore()
    executor = NodeExecutor(handlers)
    engine = WorkflowEngine(executor, checkpoints=checkpoints)
    context = WorkflowContext(workflow_id="wf-1")

    execution = await engine.run(compile_workflow(_linear_definition()), context)

    assert checkpoints.has_checkpoint(execution.execution_id) is True
    checkpoint = checkpoints.restore(execution.execution_id)
    assert "task" in checkpoint.completed_node_ids


# --- engine.py: events ---


async def test_engine_emits_workflow_and_task_events_in_order() -> None:
    handlers = NodeHandlerRegistry()

    async def task_handler(_node: NodeDefinition, _context: WorkflowContext) -> str:
        return "done"

    handlers.register(NodeType.TASK, task_handler)
    emitted: list[str] = []

    async def on_event(event: WorkflowEvent) -> None:
        emitted.append(event.event_name)

    executor = NodeExecutor(handlers)
    engine = WorkflowEngine(executor, on_event=on_event)
    context = WorkflowContext(workflow_id="wf-1")

    await engine.run(compile_workflow(_linear_definition()), context)

    assert emitted[0] == "workflow.started"
    assert emitted[-1] == "workflow.completed"
    assert "workflow.task.started" in emitted
    assert "workflow.task.completed" in emitted


# --- engine.py: telemetry ---


async def test_engine_creates_a_root_span_and_step_spans() -> None:
    handlers = NodeHandlerRegistry()

    async def task_handler(_node: NodeDefinition, _context: WorkflowContext) -> str:
        return "done"

    handlers.register(NodeType.TASK, task_handler)
    provider, exporter = _provider()
    tracer = provider.get_tracer(__name__)
    executor = NodeExecutor(handlers)
    engine = WorkflowEngine(executor, tracer=tracer)
    context = WorkflowContext(workflow_id="wf-1")

    await engine.run(compile_workflow(_linear_definition()), context)

    span_names = [span.name for span in exporter.get_finished_spans()]
    assert any(name.startswith("workflow.wf-1") for name in span_names)
    assert any("step" in name for name in span_names)


# --- runtime.py ---


async def test_runtime_start_does_not_block_and_wait_returns_the_result() -> None:
    handlers = NodeHandlerRegistry()

    async def task_handler(_node: NodeDefinition, _context: WorkflowContext) -> None:
        await asyncio.sleep(0.05)

    handlers.register(NodeType.TASK, task_handler)
    executor = NodeExecutor(handlers)
    engine = WorkflowEngine(executor)
    runtime = WorkflowRuntime(engine)
    compiled = compile_workflow(_linear_definition())
    context = WorkflowContext(workflow_id="wf-1")

    execution_id = await runtime.start(compiled, context)

    assert runtime.is_running(execution_id) is True
    execution = await runtime.wait(execution_id)

    assert execution.status == WorkflowState.COMPLETED
    assert runtime.is_running(execution_id) is False


async def test_runtime_cancel_stops_a_running_execution() -> None:
    handlers = NodeHandlerRegistry()

    async def slow_task(_node: NodeDefinition, _context: WorkflowContext) -> None:
        await asyncio.sleep(10)

    handlers.register(NodeType.TASK, slow_task)
    executor = NodeExecutor(handlers)
    engine = WorkflowEngine(executor)
    runtime = WorkflowRuntime(engine)
    compiled = compile_workflow(_linear_definition())
    context = WorkflowContext(workflow_id="wf-1")

    execution_id = await runtime.start(compiled, context)
    runtime.cancel(execution_id)

    with pytest.raises(asyncio.CancelledError):
        await runtime.wait(execution_id)


def test_runtime_list_execution_ids_and_discard() -> None:
    engine = _engine()
    runtime = WorkflowRuntime(engine)

    assert runtime.list_execution_ids() == []
    runtime.discard("missing")  # no-op


def test_runtime_raises_for_unknown_execution_id() -> None:
    engine = _engine()
    runtime = WorkflowRuntime(engine)

    with pytest.raises(WorkflowNotFoundError):
        runtime.is_running("missing")
    with pytest.raises(WorkflowNotFoundError):
        runtime.cancel("missing")
