"""Runs one :class:`~app.models.workflow.AgentWorkflow`'s own
``graph_definition`` through the real ``shared_core.workflow``
engine, persisting checkpoints and final state onto that same row
(docs/060's own "LangGraph-style workflow persistence" note).

``context.execution_id`` is deliberately set equal to
``str(workflow.id)`` -- this service's own durable database identity --
rather than the SDK's own randomly-generated execution id, the same
identity-collapsing choice ``workflow-runtime-service``'s own
``app/services/execution.py`` already makes and explains: it is what
lets a later resume recover the owning row with no separate lookup
table.
"""

from __future__ import annotations

from datetime import UTC, datetime

from shared_core.workflow import (
    NodeExecutor,
    NodeHandlerRegistry,
    WorkflowContext,
    WorkflowEngine,
    WorkflowExecution,
)
from shared_core.workflow.approval import ApprovalDecision, ApprovalRequest
from shared_core.workflow.compiler import compile_workflow
from shared_core.workflow.parser import parse_dict
from shared_core.workflow.variables import VariableScope

from app.agents.orchestrator import AgentOrchestrator
from app.langgraph.approval import (
    AWAITING_APPROVAL_PREFIX,
    approval_request_from_dict,
    approval_request_to_dict,
    register_approval_node_handler,
)
from app.langgraph.checkpoint import PersistentCheckpointStore, checkpoint_from_dict
from app.langgraph.handlers import register_ai_node_handler
from app.langgraph.status import from_sdk_state
from app.models.enums import WorkflowRunStatus
from app.models.workflow import AgentWorkflow
from app.repositories.workflow import AgentWorkflowRepository

_SOURCE_SERVICE = "ai-agent-platform-service"
_PENDING_APPROVAL_KEY = "pending_approval"
_VARIABLES_KEY = "variables_snapshot"


class WorkflowPersistenceService:
    """Executes and durably persists one multi-agent workflow run."""

    def __init__(self, workflows: AgentWorkflowRepository, orchestrator: AgentOrchestrator) -> None:
        self._workflows = workflows
        self._orchestrator = orchestrator

    async def run(self, workflow: AgentWorkflow) -> AgentWorkflow:
        """Compile *workflow*'s own ``graph_definition``, run it to
        completion, failure, or a human-approval pause, and persist
        every durable side effect -- status, current position, latest
        checkpoint, pending approval, and any error -- onto *workflow*
        itself.

        Every durable write happens only *after* ``await engine.run(...)``
        returns, since ``shared_core.workflow.execution.WorkflowExecution``
        is a purely in-memory object the SDK never exposes mid-run.

        Re-running a workflow that previously paused for approval
        re-executes the *whole* graph from ``START`` -- see
        :mod:`app.langgraph.approval`'s own module docstring for why
        that is this SDK's real, confirmed limit, not a design choice.
        """
        definition = parse_dict(workflow.graph_definition)
        compiled = compile_workflow(definition)

        checkpoint_store = PersistentCheckpointStore()
        if workflow.checkpoint:
            checkpoint_store.save(checkpoint_from_dict(workflow.checkpoint))

        context = WorkflowContext(
            workflow_id=definition.workflow_id,
            execution_id=str(workflow.id),
            organization_id=str(workflow.organization_id),
        )
        for name, value in (workflow.checkpoint.get(_VARIABLES_KEY) or {}).items():
            context.variables.set(name, value, scope=VariableScope.WORKFLOW)

        pending_holder: dict[str, ApprovalRequest] = {}

        async def resolve_approval(request_id: str) -> ApprovalRequest | None:
            if request_id in pending_holder:
                return pending_holder[request_id]
            stored = workflow.checkpoint.get(_PENDING_APPROVAL_KEY)
            if stored and stored.get("request_id") == request_id:
                return approval_request_from_dict(stored)
            return None

        async def create_approval(request: ApprovalRequest) -> None:
            pending_holder[request.request_id] = request

        handlers = NodeHandlerRegistry()
        register_ai_node_handler(handlers, self._orchestrator)
        register_approval_node_handler(handlers, resolve=resolve_approval, create=create_approval)

        engine = WorkflowEngine(
            NodeExecutor(handlers), checkpoints=checkpoint_store, source_service=_SOURCE_SERVICE
        )

        workflow.status = WorkflowRunStatus.RUNNING
        workflow.started_at = workflow.started_at or datetime.now(UTC)
        workflow = await self._workflows.update(workflow)

        try:
            execution = await engine.run(compiled, context)
        except Exception as exc:
            workflow.status = WorkflowRunStatus.FAILED
            workflow.error = str(exc)
            workflow.completed_at = datetime.now(UTC)
            return await self._workflows.update(workflow)

        pending_checkpoints = checkpoint_store.drain_pending()
        # Merged onto the existing checkpoint, never replaced wholesale -- this dict
        # also carries this platform's own extra keys (pending_approval, override_*)
        # that the SDK's own Checkpoint shape knows nothing about.
        next_checkpoint = dict(workflow.checkpoint) if workflow.checkpoint else {}
        if pending_checkpoints:
            latest = pending_checkpoints[-1]
            next_checkpoint.update(
                {
                    "execution_id": latest.execution_id,
                    "state": str(latest.state),
                    "completed_node_ids": list(latest.completed_node_ids),
                    _VARIABLES_KEY: dict(latest.variables_snapshot),
                    "created_at": latest.created_at.isoformat(),
                    "manual": latest.manual,
                }
            )
            workflow.current_node_id = (
                latest.completed_node_ids[-1] if latest.completed_node_ids else None
            )

        awaiting = self._find_awaiting_approval(execution, pending_holder, workflow)
        if awaiting is not None:
            next_checkpoint[_PENDING_APPROVAL_KEY] = approval_request_to_dict(awaiting)
            workflow.checkpoint = next_checkpoint
            workflow.status = WorkflowRunStatus.PAUSED_FOR_APPROVAL
            workflow.error = None
            return await self._workflows.update(workflow)

        next_checkpoint.pop(_PENDING_APPROVAL_KEY, None)
        workflow.checkpoint = next_checkpoint
        workflow.status = from_sdk_state(execution.status)
        workflow.error = self._first_node_error(execution)
        workflow.completed_at = datetime.now(UTC)
        return await self._workflows.update(workflow)

    @staticmethod
    def _first_node_error(execution: WorkflowExecution) -> str | None:
        """The first failed node's own error message, or ``None`` when
        every node completed cleanly.

        ``execution.status`` alone only says *that* the run failed --
        this is what actually failed, for ``workflow.error``.
        """
        for result in execution.node_results.values():
            if result.error:
                return result.error
        return None

    @staticmethod
    def _find_awaiting_approval(
        execution: WorkflowExecution,
        pending_holder: dict[str, ApprovalRequest],
        workflow: AgentWorkflow,
    ) -> ApprovalRequest | None:
        """Find the ``AWAITING_APPROVAL`` signal among this run's own
        node results, per :mod:`app.langgraph.approval`'s own
        docstring on why a message prefix is the only channel
        available.

        Searches for the prefix *anywhere* in the message, not just at
        its start: ``NodeExecutor.execute()`` wraps every handler
        exception into ``"Node '{node_id}' failed: {exc}"`` before it
        ever reaches ``node_results``, confirmed by reading its own
        source (``shared_core/workflow/executor.py``).
        """
        for result in execution.node_results.values():
            error = result.error or ""
            if AWAITING_APPROVAL_PREFIX not in error:
                continue
            request_id = error.split(AWAITING_APPROVAL_PREFIX, 1)[1]
            if request_id in pending_holder:
                return pending_holder[request_id]
            stored = workflow.checkpoint.get(_PENDING_APPROVAL_KEY)
            if stored and stored.get("request_id") == request_id:
                return approval_request_from_dict(stored)
        return None


class ApprovalService:
    """Decides, overrides, or clarifies a paused workflow's own pending
    approval, then resumes it ("Resume Execution", "Manual Overrides").
    """

    def __init__(
        self, workflows: AgentWorkflowRepository, persistence: WorkflowPersistenceService
    ) -> None:
        self._workflows = workflows
        self._persistence = persistence

    def _require_pending(self, workflow: AgentWorkflow) -> ApprovalRequest:
        stored = workflow.checkpoint.get(_PENDING_APPROVAL_KEY)
        if not stored:
            raise ValueError(f"Workflow {workflow.id!s} has no pending approval.")
        return approval_request_from_dict(stored)

    async def decide(
        self, workflow: AgentWorkflow, *, approver: str, approve: bool
    ) -> AgentWorkflow:
        """Record one approver's decision ("Approval Requests"/"Review
        Tasks"). Resumes automatically once the request resolves
        (approved or rejected); stays paused if more approvals are
        still required ("Multi-Level Approval").
        """
        request = self._require_pending(workflow)
        if approve:
            request.approve(approver)
        else:
            request.reject(approver)
        workflow.checkpoint = {
            **workflow.checkpoint,
            _PENDING_APPROVAL_KEY: approval_request_to_dict(request),
        }
        workflow = await self._workflows.update(workflow)

        if request.decision == ApprovalDecision.PENDING:
            return workflow
        return await self._persistence.run(workflow)

    async def provide_clarification(
        self, workflow: AgentWorkflow, *, answer: str, provided_by: str
    ) -> AgentWorkflow:
        """ "Clarification Requests" -- record a free-text answer as the
        approval, carrying it forward as a workflow variable the graph
        can read after resuming.
        """
        request = self._require_pending(workflow)
        request.approve(provided_by)
        variables = dict(workflow.checkpoint.get(_VARIABLES_KEY) or {})
        variables[f"{request.node_id}_clarification"] = answer
        workflow.checkpoint = {
            **workflow.checkpoint,
            _PENDING_APPROVAL_KEY: approval_request_to_dict(request),
            _VARIABLES_KEY: variables,
        }
        workflow = await self._workflows.update(workflow)
        return await self._persistence.run(workflow)

    async def override(
        self, workflow: AgentWorkflow, *, overridden_by: str, reason: str
    ) -> AgentWorkflow:
        """ "Manual Overrides" -- force-approve without a normal vote.
        The reason is recorded onto the workflow's own checkpoint so
        it survives in the same place the rest of this run's own
        "Audit Trail" already lives.
        """
        request = self._require_pending(workflow)
        request.decision = ApprovalDecision.APPROVED
        request.decisions_by_approver[overridden_by] = ApprovalDecision.APPROVED
        workflow.checkpoint = {
            **workflow.checkpoint,
            _PENDING_APPROVAL_KEY: approval_request_to_dict(request),
            "override_by": overridden_by,
            "override_reason": reason,
        }
        workflow = await self._workflows.update(workflow)
        return await self._persistence.run(workflow)


__all__ = ["ApprovalService", "WorkflowPersistenceService"]
