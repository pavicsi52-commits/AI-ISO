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
)
from shared_core.workflow.compiler import compile_workflow
from shared_core.workflow.parser import parse_dict

from app.agents.orchestrator import AgentOrchestrator
from app.langgraph.checkpoint import PersistentCheckpointStore, checkpoint_from_dict
from app.langgraph.handlers import register_ai_node_handler
from app.langgraph.status import from_sdk_state
from app.models.enums import WorkflowRunStatus
from app.models.workflow import AgentWorkflow
from app.repositories.workflow import AgentWorkflowRepository

_SOURCE_SERVICE = "ai-agent-platform-service"


class WorkflowPersistenceService:
    """Executes and durably persists one multi-agent workflow run."""

    def __init__(self, workflows: AgentWorkflowRepository, orchestrator: AgentOrchestrator) -> None:
        self._workflows = workflows
        self._orchestrator = orchestrator

    async def run(self, workflow: AgentWorkflow) -> AgentWorkflow:
        """Compile *workflow*'s own ``graph_definition``, run it to
        completion or failure, and persist every durable side effect --
        status, current position, latest checkpoint, and any error --
        onto *workflow* itself.

        Every durable write happens only *after* ``await engine.run(...)``
        returns, since ``shared_core.workflow.execution.WorkflowExecution``
        is a purely in-memory object the SDK never exposes mid-run.
        """
        definition = parse_dict(workflow.graph_definition)
        compiled = compile_workflow(definition)

        handlers = NodeHandlerRegistry()
        register_ai_node_handler(handlers, self._orchestrator)

        checkpoint_store = PersistentCheckpointStore()
        if workflow.checkpoint:
            checkpoint_store.save(checkpoint_from_dict(workflow.checkpoint))

        context = WorkflowContext(
            workflow_id=definition.workflow_id,
            execution_id=str(workflow.id),
            organization_id=str(workflow.organization_id),
        )
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

        pending = checkpoint_store.drain_pending()
        if pending:
            latest = pending[-1]
            workflow.checkpoint = {
                "execution_id": latest.execution_id,
                "state": str(latest.state),
                "completed_node_ids": list(latest.completed_node_ids),
                "variables_snapshot": dict(latest.variables_snapshot),
                "created_at": latest.created_at.isoformat(),
                "manual": latest.manual,
            }
            workflow.current_node_id = (
                latest.completed_node_ids[-1] if latest.completed_node_ids else None
            )

        workflow.status = from_sdk_state(execution.status)
        workflow.completed_at = datetime.now(UTC)
        return await self._workflows.update(workflow)


__all__ = ["WorkflowPersistenceService"]
