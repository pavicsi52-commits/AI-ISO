"""Tests for compensation.py, rollback.py, and approval.py."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from shared_core.workflow.approval import ApprovalDecision, ApprovalRequest
from shared_core.workflow.compensation import CompensationRegistry
from shared_core.workflow.context import WorkflowContext
from shared_core.workflow.exceptions import (
    ApprovalRejectedError,
    ApprovalTimeoutError,
    CompensationError,
    RollbackError,
)
from shared_core.workflow.execution import NodeExecutionResult, WorkflowExecution
from shared_core.workflow.rollback import rollback_workflow
from shared_core.workflow.state_machine import WorkflowState

# --- compensation.py ---


async def test_compensation_registry_executes_a_registered_action() -> None:
    registry = CompensationRegistry()
    calls: list[str] = []

    async def undo(_context: WorkflowContext) -> None:
        calls.append("undone")

    registry.register("n1", undo)
    context = WorkflowContext(workflow_id="wf-1")

    await registry.execute("n1", context)

    assert calls == ["undone"]


async def test_compensation_registry_execute_is_a_no_op_when_unregistered() -> None:
    registry = CompensationRegistry()
    context = WorkflowContext(workflow_id="wf-1")

    await registry.execute("missing", context)  # doesn't raise


async def test_compensation_registry_wraps_a_failing_action() -> None:
    registry = CompensationRegistry()

    async def undo(_context: WorkflowContext) -> None:
        raise RuntimeError("undo failed")

    registry.register("n1", undo)
    context = WorkflowContext(workflow_id="wf-1")

    with pytest.raises(CompensationError):
        await registry.execute("n1", context)


def test_compensation_registry_has_compensation() -> None:
    registry = CompensationRegistry()

    async def undo(_context: WorkflowContext) -> None:
        pass

    registry.register("n1", undo)

    assert registry.has_compensation("n1") is True
    assert registry.has_compensation("missing") is False


# --- rollback.py ---


def _execution_with_two_completed_nodes() -> WorkflowExecution:
    execution = WorkflowExecution(execution_id="e1", workflow_id="wf-1", workflow_version="1.0.0")
    execution.record_node_result(
        NodeExecutionResult(
            node_id="a", status=WorkflowState.COMPLETED, started_at=datetime.now(UTC)
        )
    )
    execution.record_node_result(
        NodeExecutionResult(
            node_id="b", status=WorkflowState.COMPLETED, started_at=datetime.now(UTC)
        )
    )
    return execution


async def test_rollback_workflow_compensates_in_reverse_order() -> None:
    execution = _execution_with_two_completed_nodes()
    compensations = CompensationRegistry()
    order: list[str] = []

    async def undo_a(_context: WorkflowContext) -> None:
        order.append("a")

    async def undo_b(_context: WorkflowContext) -> None:
        order.append("b")

    compensations.register("a", undo_a)
    compensations.register("b", undo_b)
    context = WorkflowContext(workflow_id="wf-1")

    compensated = await rollback_workflow(execution, compensations, context)

    assert compensated == ["b", "a"]
    assert order == ["b", "a"]
    assert execution.node_results["a"].status == WorkflowState.ROLLED_BACK
    assert execution.node_results["b"].status == WorkflowState.ROLLED_BACK


async def test_rollback_workflow_skips_nodes_without_compensation() -> None:
    execution = _execution_with_two_completed_nodes()
    compensations = CompensationRegistry()

    async def undo_a(_context: WorkflowContext) -> None:
        pass

    compensations.register("a", undo_a)
    context = WorkflowContext(workflow_id="wf-1")

    compensated = await rollback_workflow(execution, compensations, context)

    assert compensated == ["a"]
    assert execution.node_results["b"].status == WorkflowState.COMPLETED  # untouched


async def test_rollback_workflow_partial_rollback_restricts_to_given_nodes() -> None:
    execution = _execution_with_two_completed_nodes()
    compensations = CompensationRegistry()

    async def undo(_context: WorkflowContext) -> None:
        pass

    compensations.register("a", undo)
    compensations.register("b", undo)
    context = WorkflowContext(workflow_id="wf-1")

    compensated = await rollback_workflow(execution, compensations, context, node_ids=["a"])

    assert compensated == ["a"]


async def test_rollback_workflow_raises_and_preserves_partial_progress() -> None:
    execution = _execution_with_two_completed_nodes()
    compensations = CompensationRegistry()

    async def undo_a(_context: WorkflowContext) -> None:
        raise RuntimeError("boom")

    async def undo_b(_context: WorkflowContext) -> None:
        pass

    compensations.register("a", undo_a)
    compensations.register("b", undo_b)
    context = WorkflowContext(workflow_id="wf-1")

    with pytest.raises(RollbackError):
        await rollback_workflow(execution, compensations, context)

    assert execution.node_results["b"].status == WorkflowState.ROLLED_BACK
    assert execution.node_results["a"].status == WorkflowState.COMPLETED


# --- approval.py ---


def test_approval_request_starts_pending() -> None:
    request = ApprovalRequest(request_id="r1", node_id="n1", approvers=("alice",))

    assert request.decision == ApprovalDecision.PENDING


def test_approval_request_single_approver_resolves_immediately() -> None:
    request = ApprovalRequest(request_id="r1", node_id="n1", approvers=("alice",))

    request.approve("alice")

    assert request.decision == ApprovalDecision.APPROVED


def test_approval_request_multi_level_requires_every_approval() -> None:
    request = ApprovalRequest(
        request_id="r1", node_id="n1", approvers=("alice", "bob"), required_approvals=2
    )

    request.approve("alice")
    decision_after_first = request.decision
    assert decision_after_first == ApprovalDecision.PENDING

    request.approve("bob")
    decision_after_second = request.decision
    assert decision_after_second == ApprovalDecision.APPROVED


def test_approval_request_reject_resolves_immediately() -> None:
    request = ApprovalRequest(
        request_id="r1", node_id="n1", approvers=("alice", "bob"), required_approvals=2
    )

    request.approve("alice")
    request.reject("bob")

    assert request.decision == ApprovalDecision.REJECTED


def test_approval_request_escalate() -> None:
    request = ApprovalRequest(request_id="r1", node_id="n1", approvers=("alice",))

    request.escalate(to="manager")

    assert request.decision == ApprovalDecision.ESCALATED
    assert request.delegated_to == "manager"


def test_approval_request_delegate_stays_pending() -> None:
    request = ApprovalRequest(request_id="r1", node_id="n1", approvers=("alice",))

    request.delegate(to="bob")

    assert request.decision == ApprovalDecision.PENDING
    assert request.delegated_to == "bob"


def test_approval_request_mark_reminder_sent() -> None:
    request = ApprovalRequest(request_id="r1", node_id="n1", approvers=("alice",))

    request.mark_reminder_sent()

    assert request.reminder_sent is True


def test_approval_request_is_expired_false_when_within_timeout() -> None:
    request = ApprovalRequest(
        request_id="r1", node_id="n1", approvers=("alice",), timeout_seconds=3600
    )

    assert request.is_expired(now=request.created_at) is False


def test_approval_request_is_expired_true_past_timeout() -> None:
    request = ApprovalRequest(
        request_id="r1", node_id="n1", approvers=("alice",), timeout_seconds=60
    )

    later = request.created_at + timedelta(seconds=61)

    assert request.is_expired(now=later) is True


def test_approval_request_is_expired_false_once_decided() -> None:
    request = ApprovalRequest(
        request_id="r1", node_id="n1", approvers=("alice",), timeout_seconds=60
    )
    request.approve("alice")
    later = request.created_at + timedelta(seconds=120)

    assert request.is_expired(now=later) is False


def test_approval_request_resolve_returns_the_decision() -> None:
    request = ApprovalRequest(request_id="r1", node_id="n1", approvers=("alice",))
    request.approve("alice")

    assert request.resolve() == ApprovalDecision.APPROVED


def test_approval_request_resolve_raises_when_rejected() -> None:
    request = ApprovalRequest(request_id="r1", node_id="n1", approvers=("alice",))
    request.reject("alice")

    with pytest.raises(ApprovalRejectedError):
        request.resolve()


def test_approval_request_resolve_raises_when_expired() -> None:
    request = ApprovalRequest(
        request_id="r1", node_id="n1", approvers=("alice",), timeout_seconds=60
    )
    later = request.created_at + timedelta(seconds=120)

    with pytest.raises(ApprovalTimeoutError):
        request.resolve(now=later)

    assert request.decision == ApprovalDecision.EXPIRED
