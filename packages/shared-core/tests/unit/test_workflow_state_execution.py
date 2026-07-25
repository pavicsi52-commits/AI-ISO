"""Tests for state_machine.py, execution.py, checkpoint.py, retry.py,
timeout.py, and parallel.py.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from shared_core.connectors.exceptions import CircuitBreakerOpenError
from shared_core.workflow.checkpoint import Checkpoint, CheckpointStore
from shared_core.workflow.exceptions import (
    CheckpointError,
    InvalidStateTransitionError,
    WorkflowTimeoutError,
)
from shared_core.workflow.execution import NodeExecutionResult, WorkflowExecution
from shared_core.workflow.parallel import run_parallel
from shared_core.workflow.retry import CircuitBreaker, workflow_retry_policy
from shared_core.workflow.state_machine import StateMachine, WorkflowState
from shared_core.workflow.timeout import with_timeout

# --- state_machine.py ---


def test_state_machine_starts_at_created() -> None:
    machine = StateMachine()

    assert machine.state == WorkflowState.CREATED
    assert machine.history == [WorkflowState.CREATED]


def test_state_machine_valid_transition() -> None:
    machine = StateMachine()

    machine.transition(WorkflowState.PENDING)

    assert machine.state == WorkflowState.PENDING
    assert machine.history == [WorkflowState.CREATED, WorkflowState.PENDING]


def test_state_machine_invalid_transition_raises() -> None:
    machine = StateMachine()

    with pytest.raises(InvalidStateTransitionError):
        machine.transition(WorkflowState.COMPLETED)


def test_state_machine_can_transition_check() -> None:
    machine = StateMachine()

    assert machine.can_transition(WorkflowState.PENDING) is True
    assert machine.can_transition(WorkflowState.COMPLETED) is False


def test_state_machine_full_happy_path() -> None:
    machine = StateMachine()
    for target in (WorkflowState.PENDING, WorkflowState.RUNNING, WorkflowState.COMPLETED):
        machine.transition(target)

    assert machine.state == WorkflowState.COMPLETED
    assert machine.is_terminal() is False  # COMPLETED can still go to ARCHIVED


def test_state_machine_archived_is_terminal() -> None:
    machine = StateMachine()
    path = (
        WorkflowState.PENDING,
        WorkflowState.RUNNING,
        WorkflowState.COMPLETED,
        WorkflowState.ARCHIVED,
    )
    for target in path:
        machine.transition(target)

    assert machine.is_terminal() is True


def test_state_machine_supports_custom_transitions() -> None:
    custom = {
        WorkflowState.CREATED: frozenset({WorkflowState.COMPLETED}),
        WorkflowState.COMPLETED: frozenset(),
    }
    machine = StateMachine(transitions=custom)

    machine.transition(WorkflowState.COMPLETED)

    assert machine.state == WorkflowState.COMPLETED


def test_workflow_state_covers_every_documented_state() -> None:
    expected = {
        "created",
        "pending",
        "running",
        "paused",
        "waiting",
        "retrying",
        "completed",
        "cancelled",
        "failed",
        "rolled_back",
        "archived",
    }
    assert {state.value for state in WorkflowState} == expected


# --- execution.py ---


def test_node_execution_result_duration_none_while_running() -> None:
    result = NodeExecutionResult(
        node_id="n1", status=WorkflowState.RUNNING, started_at=datetime.now(UTC)
    )

    assert result.duration_seconds is None


def test_node_execution_result_duration_computed_when_finished() -> None:
    started = datetime.now(UTC)
    result = NodeExecutionResult(
        node_id="n1",
        status=WorkflowState.COMPLETED,
        started_at=started,
        finished_at=started + timedelta(seconds=3),
    )

    assert result.duration_seconds == 3.0


def test_workflow_execution_status_reflects_state_machine() -> None:
    execution = WorkflowExecution(execution_id="e1", workflow_id="wf-1", workflow_version="1.0.0")

    assert execution.status == WorkflowState.CREATED


def test_workflow_execution_record_and_completed_node_ids() -> None:
    execution = WorkflowExecution(execution_id="e1", workflow_id="wf-1", workflow_version="1.0.0")
    execution.record_node_result(
        NodeExecutionResult(
            node_id="a", status=WorkflowState.COMPLETED, started_at=datetime.now(UTC)
        )
    )
    execution.record_node_result(
        NodeExecutionResult(node_id="b", status=WorkflowState.FAILED, started_at=datetime.now(UTC))
    )

    assert execution.completed_node_ids() == ["a"]


# --- checkpoint.py ---


def test_checkpoint_store_save_and_restore() -> None:
    store = CheckpointStore()
    checkpoint = Checkpoint(
        execution_id="e1",
        state=WorkflowState.RUNNING,
        completed_node_ids=("a",),
        variables_snapshot={"x": 1},
    )

    store.save(checkpoint)

    assert store.restore("e1") is checkpoint


def test_checkpoint_store_restore_raises_when_missing() -> None:
    store = CheckpointStore()

    with pytest.raises(CheckpointError):
        store.restore("missing")


def test_checkpoint_store_has_checkpoint() -> None:
    store = CheckpointStore()
    store.save(
        Checkpoint(
            execution_id="e1",
            state=WorkflowState.RUNNING,
            completed_node_ids=(),
            variables_snapshot={},
        )
    )

    assert store.has_checkpoint("e1") is True
    assert store.has_checkpoint("missing") is False


def test_checkpoint_store_discard() -> None:
    store = CheckpointStore()
    store.save(
        Checkpoint(
            execution_id="e1",
            state=WorkflowState.RUNNING,
            completed_node_ids=(),
            variables_snapshot={},
        )
    )

    store.discard("e1")

    assert store.has_checkpoint("e1") is False


def test_checkpoint_store_discard_unknown_is_a_no_op() -> None:
    store = CheckpointStore()

    store.discard("missing")


# --- retry.py ---


def test_workflow_retry_policy_default_max_attempts() -> None:
    policy = workflow_retry_policy()

    assert policy.max_attempts == 3


def test_circuit_breaker_is_reused_from_connectors() -> None:
    breaker = CircuitBreaker(failure_threshold=1)

    breaker.before_call()
    breaker.record_failure()

    with pytest.raises(CircuitBreakerOpenError):
        breaker.before_call()


# --- timeout.py ---


async def test_with_timeout_returns_the_result_when_fast_enough() -> None:
    async def fast() -> str:
        return "done"

    result = await with_timeout(fast(), timeout_seconds=1, operation="fast op")

    assert result == "done"


async def test_with_timeout_raises_when_too_slow() -> None:
    async def slow() -> str:
        await asyncio.sleep(10)
        return "done"

    with pytest.raises(WorkflowTimeoutError):
        await with_timeout(slow(), timeout_seconds=0.01, operation="slow op")


# --- parallel.py ---


async def test_run_parallel_collects_every_branchs_success() -> None:
    async def branch_a() -> str:
        return "a-result"

    async def branch_b() -> str:
        return "b-result"

    results = await run_parallel({"a": branch_a, "b": branch_b})

    by_id = {result.branch_id: result for result in results}
    assert by_id["a"].succeeded is True
    assert by_id["a"].value == "a-result"
    assert by_id["b"].succeeded is True


async def test_run_parallel_captures_a_failing_branch_without_cancelling_others() -> None:
    async def failing() -> str:
        raise RuntimeError("boom")

    async def succeeding() -> str:
        return "ok"

    results = await run_parallel({"fail": failing, "ok": succeeding})

    by_id = {result.branch_id: result for result in results}
    assert by_id["fail"].succeeded is False
    assert isinstance(by_id["fail"].error, RuntimeError)
    assert by_id["ok"].succeeded is True


async def test_run_parallel_respects_max_concurrency() -> None:
    active = 0
    max_active = 0

    async def branch() -> None:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.05)
        active -= 1

    branches: dict[str, Callable[[], Awaitable[None]]] = {f"b{i}": branch for i in range(5)}
    await run_parallel(branches, max_concurrency=2)

    assert max_active <= 2
