"""Tests for :mod:`app.langgraph` -- status translation, checkpoint
persistence, human-in-the-loop approval, the ``AI`` node handler, and
``WorkflowPersistenceService``/``ApprovalService`` running the real
``shared_core.workflow`` engine end to end.

Node retries. ``shared_core.workflow``'s default retry policy retries
any ``TaskExecutionError`` (the only exception the ``AI``/``APPROVAL``
handlers ever raise) up to 3 times with backoff before the engine gives
up on that node -- so any test that drives a *first* pause or a real
model dispatch through the full engine pays a few seconds of real
backoff delay. That is the SDK's own behavior, not a test bug; kept to
the minimum number of engine-level tests actually needed for that
reason, with the rest of this module's own logic (status mapping,
checkpoint round-trips, the approval/AI handlers in isolation, and
``WorkflowPersistenceService``'s own static helpers) tested directly
and fast.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from shared_core.workflow import (
    Checkpoint,
    NodeDefinition,
    NodeExecutionResult,
    NodeHandlerRegistry,
    NodeType,
    TaskExecutionError,
    WorkflowContext,
    WorkflowExecution,
    WorkflowState,
)
from shared_core.workflow.approval import ApprovalDecision, ApprovalRequest
from shared_core.workflow.exceptions import InvalidWorkflowDefinitionError

from app.agents.orchestrator import AgentOrchestrator
from app.langgraph.approval import (
    AWAITING_APPROVAL_PREFIX,
    approval_request_from_dict,
    approval_request_to_dict,
    build_approval_node_handler,
    register_approval_node_handler,
)
from app.langgraph.checkpoint import (
    PersistentCheckpointStore,
    checkpoint_from_dict,
    checkpoint_to_dict,
)
from app.langgraph.handlers import build_ai_node_handler, register_ai_node_handler
from app.langgraph.service import ApprovalService, WorkflowPersistenceService
from app.langgraph.status import from_sdk_state, to_sdk_state
from app.models.enums import AgentType, WorkflowRunStatus
from app.models.workflow import AgentWorkflow
from tests.conftest import utcnow

# ---- status.py --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sdk_state", "expected"),
    [
        (WorkflowState.CREATED, WorkflowRunStatus.PENDING),
        (WorkflowState.PENDING, WorkflowRunStatus.PENDING),
        (WorkflowState.RUNNING, WorkflowRunStatus.RUNNING),
        (WorkflowState.PAUSED, WorkflowRunStatus.PAUSED_FOR_APPROVAL),
        (WorkflowState.WAITING, WorkflowRunStatus.RUNNING),
        (WorkflowState.RETRYING, WorkflowRunStatus.RUNNING),
        (WorkflowState.COMPLETED, WorkflowRunStatus.COMPLETED),
        (WorkflowState.CANCELLED, WorkflowRunStatus.CANCELLED),
        (WorkflowState.FAILED, WorkflowRunStatus.FAILED),
        (WorkflowState.ROLLED_BACK, WorkflowRunStatus.FAILED),
        (WorkflowState.ARCHIVED, WorkflowRunStatus.COMPLETED),
    ],
)
def test_from_sdk_state_maps_every_sdk_state(sdk_state: WorkflowState, expected: WorkflowRunStatus):
    assert from_sdk_state(sdk_state) == expected


def test_from_sdk_state_accepts_a_plain_string():
    assert from_sdk_state("running") == WorkflowRunStatus.RUNNING


@pytest.mark.parametrize(
    ("run_status", "expected"),
    [
        (WorkflowRunStatus.PENDING, WorkflowState.PENDING),
        (WorkflowRunStatus.RUNNING, WorkflowState.RUNNING),
        (WorkflowRunStatus.PAUSED_FOR_APPROVAL, WorkflowState.PAUSED),
        (WorkflowRunStatus.COMPLETED, WorkflowState.COMPLETED),
        (WorkflowRunStatus.FAILED, WorkflowState.FAILED),
        (WorkflowRunStatus.CANCELLED, WorkflowState.CANCELLED),
    ],
)
def test_to_sdk_state_maps_every_run_status(run_status: WorkflowRunStatus, expected: WorkflowState):
    assert to_sdk_state(run_status) == expected


def test_to_sdk_state_accepts_a_plain_string():
    assert to_sdk_state("completed") == WorkflowState.COMPLETED


@pytest.mark.parametrize("status", list(WorkflowRunStatus))
def test_status_round_trips_through_the_sdk_state(status: WorkflowRunStatus):
    assert from_sdk_state(to_sdk_state(status)) == status


# ---- checkpoint.py ------------------------------------------------------------------


def test_checkpoint_round_trip_preserves_every_field():
    checkpoint = Checkpoint(
        execution_id="exec-1",
        state=WorkflowState.RUNNING,
        completed_node_ids=("start", "mid"),
        variables_snapshot={"x": 1, "y": "z"},
        manual=True,
    )

    restored = checkpoint_from_dict(checkpoint_to_dict(checkpoint))

    assert restored == checkpoint


def test_checkpoint_from_dict_defaults_missing_optional_fields():
    restored = checkpoint_from_dict(
        {
            "execution_id": "exec-2",
            "state": "pending",
            "created_at": datetime.now(UTC).isoformat(),
        }
    )

    assert restored.completed_node_ids == ()
    assert restored.variables_snapshot == {}
    assert restored.manual is False


def test_persistent_checkpoint_store_still_behaves_like_a_plain_store():
    store = PersistentCheckpointStore()
    checkpoint = Checkpoint(
        execution_id="e1", state=WorkflowState.RUNNING, completed_node_ids=(), variables_snapshot={}
    )

    store.save(checkpoint)

    assert store.has_checkpoint("e1") is True
    assert store.restore("e1") == checkpoint
    assert store.has_checkpoint("missing") is False


def test_persistent_checkpoint_store_buffers_and_drains_every_save():
    store = PersistentCheckpointStore()
    first = Checkpoint(
        execution_id="e1", state=WorkflowState.RUNNING, completed_node_ids=(), variables_snapshot={}
    )
    second = Checkpoint(
        execution_id="e1",
        state=WorkflowState.COMPLETED,
        completed_node_ids=("a",),
        variables_snapshot={},
    )

    store.save(first)
    store.save(second)
    drained = store.drain_pending()

    assert drained == [first, second]
    assert store.drain_pending() == []


# ---- approval.py --------------------------------------------------------------------


def test_approval_request_round_trip_preserves_every_field():
    request = ApprovalRequest(
        request_id="r1",
        node_id="n1",
        approvers=("alice", "bob"),
        required_approvals=2,
        decision=ApprovalDecision.ESCALATED,
        decisions_by_approver={"alice": ApprovalDecision.APPROVED},
        delegated_to="carol",
        timeout_seconds=600.0,
        reminder_sent=True,
    )

    restored = approval_request_from_dict(approval_request_to_dict(request))

    assert restored == request


def test_approval_request_from_dict_defaults_missing_optional_fields():
    restored = approval_request_from_dict(
        {
            "request_id": "r1",
            "node_id": "n1",
            "created_at": datetime.now(UTC).isoformat(),
        }
    )

    assert restored.approvers == ()
    assert restored.required_approvals == 1
    assert restored.decision == ApprovalDecision.PENDING
    assert restored.decisions_by_approver == {}
    assert restored.timeout_seconds == 3600.0
    assert restored.reminder_sent is False


async def test_approval_handler_first_call_creates_request_and_pauses():
    created: list[ApprovalRequest] = []

    async def resolve(request_id: str) -> ApprovalRequest | None:
        return None

    async def create(request: ApprovalRequest) -> None:
        created.append(request)

    handler = build_approval_node_handler(resolve=resolve, create=create)
    node = NodeDefinition(
        node_id="gate",
        node_type=NodeType.APPROVAL,
        name="Gate",
        config={"approvers": ["alice", "bob"], "required_approvals": 2, "timeout_seconds": 120.0},
    )
    context = WorkflowContext(workflow_id="wf", execution_id="exec-1")

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler(node, context)

    assert str(exc_info.value) == f"{AWAITING_APPROVAL_PREFIX}exec-1:gate"
    assert len(created) == 1
    assert created[0].request_id == "exec-1:gate"
    assert created[0].approvers == ("alice", "bob")
    assert created[0].required_approvals == 2
    assert created[0].timeout_seconds == 120.0


async def test_approval_handler_still_pending_pauses_again_without_recreating():
    existing = ApprovalRequest(request_id="exec-1:gate", node_id="gate", approvers=())
    calls: list[ApprovalRequest] = []

    async def resolve(request_id: str) -> ApprovalRequest | None:
        return existing

    async def create(request: ApprovalRequest) -> None:
        calls.append(request)

    handler = build_approval_node_handler(resolve=resolve, create=create)
    node = NodeDefinition(node_id="gate", node_type=NodeType.APPROVAL, name="Gate")
    context = WorkflowContext(workflow_id="wf", execution_id="exec-1")

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler(node, context)

    assert AWAITING_APPROVAL_PREFIX in str(exc_info.value)
    assert calls == []


async def test_approval_handler_approved_existing_passes_through():
    existing = ApprovalRequest(
        request_id="exec-1:gate", node_id="gate", approvers=(), decision=ApprovalDecision.APPROVED
    )

    async def resolve(request_id: str) -> ApprovalRequest | None:
        return existing

    async def create(request: ApprovalRequest) -> None:
        raise AssertionError("an already-approved request must never be recreated")

    handler = build_approval_node_handler(resolve=resolve, create=create)
    node = NodeDefinition(node_id="gate", node_type=NodeType.APPROVAL, name="Gate")
    context = WorkflowContext(workflow_id="wf", execution_id="exec-1")

    result = await handler(node, context)

    assert result == {"decision": "approved", "request_id": "exec-1:gate"}


@pytest.mark.parametrize("decision", [ApprovalDecision.REJECTED, ApprovalDecision.EXPIRED])
async def test_approval_handler_terminal_negative_decision_raises_without_pause_prefix(
    decision: ApprovalDecision,
):
    existing = ApprovalRequest(
        request_id="exec-1:gate", node_id="gate", approvers=(), decision=decision
    )

    async def resolve(request_id: str) -> ApprovalRequest | None:
        return existing

    async def create(request: ApprovalRequest) -> None:
        raise AssertionError("a resolved request must never be recreated")

    handler = build_approval_node_handler(resolve=resolve, create=create)
    node = NodeDefinition(node_id="gate", node_type=NodeType.APPROVAL, name="Gate")
    context = WorkflowContext(workflow_id="wf", execution_id="exec-1")

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler(node, context)

    assert AWAITING_APPROVAL_PREFIX not in str(exc_info.value)
    assert str(decision) in str(exc_info.value)


def test_register_approval_node_handler_registers_for_approval_type():
    registry = NodeHandlerRegistry()

    async def resolve(request_id: str) -> ApprovalRequest | None:
        return None

    async def create(request: ApprovalRequest) -> None:
        return None

    register_approval_node_handler(registry, resolve=resolve, create=create)

    assert registry.get(NodeType.APPROVAL) is not None
    assert registry.get(NodeType.AI) is None


# ---- handlers.py (AI node) -----------------------------------------------------------


async def test_ai_node_handler_unknown_agent_type_raises(model_registry):
    orchestrator = AgentOrchestrator(model_registry, {}, {})
    handler = build_ai_node_handler(orchestrator)
    node = NodeDefinition(
        node_id="n1", node_type=NodeType.AI, name="N1", config={"agent_type": "not_a_real_type"}
    )
    context = WorkflowContext(workflow_id="wf", execution_id="exec-1")

    with pytest.raises(TaskExecutionError, match="unknown agent_type"):
        await handler(node, context)


async def test_ai_node_handler_wraps_a_failed_dispatch(model_registry):
    orchestrator = AgentOrchestrator(model_registry, {}, {})
    handler = build_ai_node_handler(orchestrator)
    node = NodeDefinition(node_id="n1", node_type=NodeType.AI, name="Say hi", config={})
    context = WorkflowContext(workflow_id="wf", execution_id="exec-1")

    with pytest.raises(TaskExecutionError) as exc_info:
        await handler(node, context)

    assert "AI node 'n1' failed" in str(exc_info.value)
    assert "No agent registered" in str(exc_info.value)


async def test_ai_node_handler_real_dispatch_accepts_success_or_failure(
    model_registry, make_agent, profiles_repo
):
    agent = await make_agent(slug="ai-node-agent", agent_type=AgentType.EXECUTOR)
    profile = await profiles_repo.get_for_agent(agent.id)
    orchestrator = AgentOrchestrator(
        model_registry, {AgentType.EXECUTOR: [agent]}, {agent.id: profile}
    )
    handler = build_ai_node_handler(orchestrator)
    node = NodeDefinition(
        node_id="n1",
        node_type=NodeType.AI,
        name="Say hi",
        config={"description": "Say hello in one word.", "agent_type": "executor"},
    )
    context = WorkflowContext(workflow_id="wf", execution_id="exec-1")

    try:
        result = await handler(node, context)
    except TaskExecutionError as exc:
        assert "AI node 'n1' failed" in str(exc)
    else:
        assert result["agent_name"] == agent.name
        assert context.variables.get("n1_result") == result["content"]


def test_register_ai_node_handler_registers_for_ai_type(model_registry):
    orchestrator = AgentOrchestrator(model_registry, {}, {})
    registry = NodeHandlerRegistry()

    register_ai_node_handler(registry, orchestrator)

    assert registry.get(NodeType.AI) is not None
    assert registry.get(NodeType.APPROVAL) is None


# ---- WorkflowPersistenceService -- static helpers, tested directly and fast ----------


def test_first_node_error_returns_none_when_every_node_succeeded():
    execution = WorkflowExecution(execution_id="e", workflow_id="w", workflow_version="1.0.0")
    execution.record_node_result(
        NodeExecutionResult(node_id="a", status=WorkflowState.COMPLETED, started_at=utcnow())
    )

    assert WorkflowPersistenceService._first_node_error(execution) is None


def test_first_node_error_returns_the_first_error_found():
    execution = WorkflowExecution(execution_id="e", workflow_id="w", workflow_version="1.0.0")
    execution.record_node_result(
        NodeExecutionResult(node_id="a", status=WorkflowState.COMPLETED, started_at=utcnow())
    )
    execution.record_node_result(
        NodeExecutionResult(
            node_id="b", status=WorkflowState.FAILED, started_at=utcnow(), error="boom"
        )
    )

    assert WorkflowPersistenceService._first_node_error(execution) == "boom"


def test_find_awaiting_approval_returns_none_without_the_pause_prefix():
    execution = WorkflowExecution(execution_id="e", workflow_id="w", workflow_version="1.0.0")
    execution.record_node_result(
        NodeExecutionResult(
            node_id="a", status=WorkflowState.FAILED, started_at=utcnow(), error="plain failure"
        )
    )
    workflow = AgentWorkflow(organization_id=uuid.uuid4(), graph_definition={}, checkpoint={})

    assert WorkflowPersistenceService._find_awaiting_approval(execution, {}, workflow) is None


def test_find_awaiting_approval_finds_the_request_in_the_pending_holder():
    request = ApprovalRequest(request_id="e:gate", node_id="gate", approvers=())
    execution = WorkflowExecution(execution_id="e", workflow_id="w", workflow_version="1.0.0")
    execution.record_node_result(
        NodeExecutionResult(
            node_id="gate",
            status=WorkflowState.FAILED,
            started_at=utcnow(),
            error=f"Node 'gate' failed: {AWAITING_APPROVAL_PREFIX}e:gate",
        )
    )
    workflow = AgentWorkflow(organization_id=uuid.uuid4(), graph_definition={}, checkpoint={})

    found = WorkflowPersistenceService._find_awaiting_approval(
        execution, {"e:gate": request}, workflow
    )

    assert found is request


def test_find_awaiting_approval_falls_back_to_the_stored_checkpoint():
    stored_request = ApprovalRequest(request_id="e:gate", node_id="gate", approvers=())
    execution = WorkflowExecution(execution_id="e", workflow_id="w", workflow_version="1.0.0")
    execution.record_node_result(
        NodeExecutionResult(
            node_id="gate",
            status=WorkflowState.FAILED,
            started_at=utcnow(),
            error=f"Node 'gate' failed: {AWAITING_APPROVAL_PREFIX}e:gate",
        )
    )
    workflow = AgentWorkflow(
        organization_id=uuid.uuid4(),
        graph_definition={},
        checkpoint={"pending_approval": approval_request_to_dict(stored_request)},
    )

    found = WorkflowPersistenceService._find_awaiting_approval(execution, {}, workflow)

    assert found is not None
    assert found.request_id == "e:gate"


# ---- WorkflowPersistenceService.run() -- real engine, real graphs --------------------

_TRIVIAL_GRAPH = {
    "workflow_id": "trivial",
    "name": "Trivial",
    "version": "1.0.0",
    "nodes": [
        {"node_id": "start", "node_type": "start", "name": "start"},
        {"node_id": "end", "node_type": "end", "name": "end"},
    ],
    "edges": [{"from": "start", "to": "end"}],
}


def _approval_graph(*, approvers: tuple[str, ...] = (), required_approvals: int = 1) -> dict:
    return {
        "workflow_id": "approval-wf",
        "name": "Approval",
        "version": "1.0.0",
        "nodes": [
            {"node_id": "start", "node_type": "start", "name": "start"},
            {
                "node_id": "gate",
                "node_type": "approval",
                "name": "gate",
                "config": {"approvers": list(approvers), "required_approvals": required_approvals},
            },
            {"node_id": "end", "node_type": "end", "name": "end"},
        ],
        "edges": [{"from": "start", "to": "gate"}, {"from": "gate", "to": "end"}],
    }


async def test_run_trivial_graph_completes(workflows_repo, organization_id, model_registry):
    orchestrator = AgentOrchestrator(model_registry, {}, {})
    service = WorkflowPersistenceService(workflows_repo, orchestrator)
    workflow = await workflows_repo.create(
        AgentWorkflow(
            organization_id=organization_id, graph_definition=_TRIVIAL_GRAPH, checkpoint={}
        )
    )

    result = await service.run(workflow)

    assert result.status == WorkflowRunStatus.COMPLETED
    assert result.error is None
    assert result.started_at is not None
    assert result.completed_at is not None
    # "running", not "completed": the SDK's own ``WorkflowEngine`` saves
    # each checkpoint *inside* its per-level loop, while the execution is
    # still RUNNING, and only transitions to COMPLETED after the loop
    # exits (confirmed in shared_core/workflow/engine.py). So the last
    # persisted checkpoint is by construction always a mid-run snapshot.
    # The terminal state lives on the row's own ``status`` column,
    # asserted above -- which is exactly what the checkpoint recovery
    # sweep filters on, never this field.
    assert result.checkpoint["state"] == "running"
    assert set(result.checkpoint["completed_node_ids"]) == {"start", "end"}


async def test_run_raises_for_a_structurally_invalid_graph_definition(
    workflows_repo, organization_id, model_registry
):
    orchestrator = AgentOrchestrator(model_registry, {}, {})
    service = WorkflowPersistenceService(workflows_repo, orchestrator)
    workflow = await workflows_repo.create(
        AgentWorkflow(
            organization_id=organization_id, graph_definition={"nodes": []}, checkpoint={}
        )
    )

    with pytest.raises(InvalidWorkflowDefinitionError):
        await service.run(workflow)


async def test_run_graph_with_ai_node_dispatches_through_the_real_orchestrator(
    workflows_repo, organization_id, make_agent, profiles_repo, model_registry
):
    agent = await make_agent(slug="wf-ai-agent", agent_type=AgentType.EXECUTOR)
    profile = await profiles_repo.get_for_agent(agent.id)
    orchestrator = AgentOrchestrator(
        model_registry, {AgentType.EXECUTOR: [agent]}, {agent.id: profile}
    )
    service = WorkflowPersistenceService(workflows_repo, orchestrator)
    graph = {
        "workflow_id": "ai-wf",
        "name": "AI",
        "version": "1.0.0",
        "nodes": [
            {"node_id": "start", "node_type": "start", "name": "start"},
            {
                "node_id": "ask",
                "node_type": "ai",
                "name": "ask",
                "config": {"description": "Say hello in one word.", "agent_type": "executor"},
            },
            {"node_id": "end", "node_type": "end", "name": "end"},
        ],
        "edges": [{"from": "start", "to": "ask"}, {"from": "ask", "to": "end"}],
    }
    workflow = await workflows_repo.create(
        AgentWorkflow(organization_id=organization_id, graph_definition=graph, checkpoint={})
    )

    result = await service.run(workflow)

    assert result.status in (WorkflowRunStatus.COMPLETED, WorkflowRunStatus.FAILED)
    if result.status == WorkflowRunStatus.COMPLETED:
        assert result.error is None
        assert set(result.checkpoint["completed_node_ids"]) == {"start", "ask", "end"}
    else:
        assert result.error


async def test_run_pauses_for_approval_then_resumes_on_decide(
    workflows_repo, organization_id, model_registry
):
    orchestrator = AgentOrchestrator(model_registry, {}, {})
    service = WorkflowPersistenceService(workflows_repo, orchestrator)
    approvals = ApprovalService(workflows_repo, service)
    workflow = await workflows_repo.create(
        AgentWorkflow(
            organization_id=organization_id,
            graph_definition=_approval_graph(approvers=("alice",)),
            checkpoint={},
        )
    )

    paused = await service.run(workflow)

    assert paused.status == WorkflowRunStatus.PAUSED_FOR_APPROVAL
    assert paused.error is None
    pending = paused.checkpoint["pending_approval"]
    assert pending["decision"] == "pending"
    assert pending["request_id"] == f"{paused.id!s}:gate"

    resumed = await approvals.decide(paused, approver="alice", approve=True)

    assert resumed.status == WorkflowRunStatus.COMPLETED
    assert resumed.error is None
    assert "pending_approval" not in resumed.checkpoint
    assert set(resumed.checkpoint["completed_node_ids"]) == {"start", "gate", "end"}


async def test_run_rejection_resumes_into_a_failed_workflow(
    workflows_repo, organization_id, model_registry
):
    orchestrator = AgentOrchestrator(model_registry, {}, {})
    service = WorkflowPersistenceService(workflows_repo, orchestrator)
    approvals = ApprovalService(workflows_repo, service)
    workflow = await workflows_repo.create(
        AgentWorkflow(
            organization_id=organization_id,
            graph_definition=_approval_graph(approvers=("alice",)),
            checkpoint={},
        )
    )
    paused = await service.run(workflow)

    rejected = await approvals.decide(paused, approver="alice", approve=False)

    assert rejected.status == WorkflowRunStatus.FAILED
    assert rejected.error is not None
    assert "rejected" in rejected.error.lower()
    assert "pending_approval" not in rejected.checkpoint


async def test_decide_stays_paused_until_required_approvals_are_met(
    workflows_repo, organization_id, model_registry
):
    orchestrator = AgentOrchestrator(model_registry, {}, {})
    service = WorkflowPersistenceService(workflows_repo, orchestrator)
    approvals = ApprovalService(workflows_repo, service)
    workflow = await workflows_repo.create(
        AgentWorkflow(
            organization_id=organization_id,
            graph_definition=_approval_graph(approvers=("alice", "bob"), required_approvals=2),
            checkpoint={},
        )
    )
    paused = await service.run(workflow)

    still_pending = await approvals.decide(paused, approver="alice", approve=True)

    assert still_pending.status == WorkflowRunStatus.PAUSED_FOR_APPROVAL
    pending = still_pending.checkpoint["pending_approval"]
    assert pending["decision"] == "pending"
    assert pending["decisions_by_approver"]["alice"] == "approved"

    resumed = await approvals.decide(still_pending, approver="bob", approve=True)

    assert resumed.status == WorkflowRunStatus.COMPLETED


async def test_override_force_approves_regardless_of_required_approvals(
    workflows_repo, organization_id, model_registry
):
    orchestrator = AgentOrchestrator(model_registry, {}, {})
    service = WorkflowPersistenceService(workflows_repo, orchestrator)
    approvals = ApprovalService(workflows_repo, service)
    workflow = await workflows_repo.create(
        AgentWorkflow(
            organization_id=organization_id,
            graph_definition=_approval_graph(approvers=("alice",), required_approvals=5),
            checkpoint={},
        )
    )
    paused = await service.run(workflow)

    overridden = await approvals.override(
        paused, overridden_by="admin", reason="manual override for testing"
    )

    assert overridden.status == WorkflowRunStatus.COMPLETED
    assert overridden.checkpoint["override_by"] == "admin"
    assert overridden.checkpoint["override_reason"] == "manual override for testing"


async def test_provide_clarification_records_the_answer_and_resumes(
    workflows_repo, organization_id, model_registry
):
    orchestrator = AgentOrchestrator(model_registry, {}, {})
    service = WorkflowPersistenceService(workflows_repo, orchestrator)
    approvals = ApprovalService(workflows_repo, service)
    workflow = await workflows_repo.create(
        AgentWorkflow(
            organization_id=organization_id,
            graph_definition=_approval_graph(approvers=("alice",)),
            checkpoint={},
        )
    )
    paused = await service.run(workflow)

    clarified = await approvals.provide_clarification(
        paused, answer="Yes, proceed.", provided_by="alice"
    )

    assert clarified.status == WorkflowRunStatus.COMPLETED
    assert clarified.checkpoint["variables_snapshot"]["gate_clarification"] == "Yes, proceed."


async def test_decide_raises_without_a_pending_approval(
    workflows_repo, organization_id, model_registry
):
    orchestrator = AgentOrchestrator(model_registry, {}, {})
    service = WorkflowPersistenceService(workflows_repo, orchestrator)
    approvals = ApprovalService(workflows_repo, service)
    workflow = await workflows_repo.create(
        AgentWorkflow(organization_id=organization_id, graph_definition={}, checkpoint={})
    )

    with pytest.raises(ValueError, match="has no pending approval"):
        await approvals.decide(workflow, approver="alice", approve=True)
