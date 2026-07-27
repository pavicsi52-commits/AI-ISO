"""The workflow instance execution orchestrator -- the analog of
``services/automation-service``'s own ``AutomationExecutionService``,
but wrapping ``shared_core.workflow.WorkflowEngine`` instead of running
connectors directly.

Builds a fresh :class:`~shared_core.workflow.NodeHandlerRegistry`/
:class:`~shared_core.workflow.CompensationRegistry`/
:class:`~app.services.checkpoint.PersistentCheckpointStore`/
:class:`~shared_core.workflow.WorkflowEngine` for every run (the SDK
gives no way to reuse one across runs with different node sets) and
persists every durable side effect -- execution steps, state
transitions, checkpoints, the final result, and platform events -- only
*after* ``await engine.run(...)`` returns, since
``shared_core.workflow.execution.WorkflowExecution`` is a purely
in-memory object the SDK never exposes mid-run (its own
``TaskCompleted``/``TaskFailed`` events carry no ``output``/``attempts``
field -- see :meth:`WorkflowExecutionService._handle_sdk_event`).

``context.execution_id`` is deliberately set equal to
``str(instance.id)`` (this service's own durable database identity)
rather than left as the SDK's own randomly-generated
:func:`~shared_core.workflow.new_execution_id` value -- this collapses
what would otherwise be two parallel identities for the same run into
one, and is what lets ``app/handlers/approval.py`` recover its own
instance id from ``context.execution_id`` with no separate lookup
table.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx
from shared_core.events.base import DomainEvent
from shared_core.workflow import (
    NodeExecutor,
    NodeHandlerRegistry,
    TaskCompletedEvent,
    TaskFailedEvent,
    TaskStartedEvent,
    WorkflowContext,
    WorkflowEngine,
    WorkflowEvent,
    WorkflowTaskQueue,
)

from app.clients.automation_client import AutomationClient
from app.events.workflow_events import (
    WorkflowCancelledEvent,
    WorkflowCompletedEvent,
    WorkflowFailedEvent,
    WorkflowRolledBackEvent,
    WorkflowStartedEvent,
)
from app.handlers.approval import register_approval_handlers
from app.handlers.event_node import register_event_handler
from app.handlers.queue_node import register_queue_handler
from app.handlers.subworkflow import register_subworkflow_and_loop_handlers
from app.handlers.task import register_task_and_connector_handlers
from app.handlers.webhook import register_webhook_handler
from app.models.enums import NodeExecutionStatus, WorkflowInstanceStatus, WorkflowTriggerType
from app.models.workflow_definition import WorkflowDefinition
from app.models.workflow_execution_step import WorkflowExecutionStep
from app.models.workflow_instance import WorkflowInstance
from app.models.workflow_result import WorkflowResult
from app.repositories.workflow_execution_step import WorkflowExecutionStepRepository
from app.repositories.workflow_instance import WorkflowInstanceRepository
from app.repositories.workflow_result import WorkflowResultRepository
from app.services.approval import WorkflowApprovalService
from app.services.checkpoint import PersistentCheckpointStore, WorkflowCheckpointService
from app.services.compensation import WorkflowCompensationService, build_compensation_registry
from app.services.compiler import compile_version
from app.services.definition import WorkflowDefinitionService
from app.services.event import WorkflowEventService
from app.services.log import WorkflowLogService
from app.services.state import WorkflowStateTransitionService
from app.services.status import from_sdk_state
from app.services.version import WorkflowVersionService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]

_TERMINAL_EVENTS: dict[WorkflowInstanceStatus, type[DomainEvent]] = {
    WorkflowInstanceStatus.COMPLETED: WorkflowCompletedEvent,
    WorkflowInstanceStatus.FAILED: WorkflowFailedEvent,
    WorkflowInstanceStatus.CANCELLED: WorkflowCancelledEvent,
    WorkflowInstanceStatus.ROLLED_BACK: WorkflowRolledBackEvent,
}

_NODE_STATUS_MAP: dict[str, NodeExecutionStatus] = {
    "completed": NodeExecutionStatus.COMPLETED,
    "failed": NodeExecutionStatus.FAILED,
    "cancelled": NodeExecutionStatus.SKIPPED,
    "rolled_back": NodeExecutionStatus.ROLLED_BACK,
}


class WorkflowExecutionService:
    """Runs one workflow instance to completion against the Workflow SDK."""

    def __init__(
        self,
        instances: WorkflowInstanceRepository,
        steps: WorkflowExecutionStepRepository,
        results: WorkflowResultRepository,
        definitions: WorkflowDefinitionService,
        versions: WorkflowVersionService,
        states: WorkflowStateTransitionService,
        logs: WorkflowLogService,
        events: WorkflowEventService,
        approvals: WorkflowApprovalService,
        checkpoints: WorkflowCheckpointService,
        compensations: WorkflowCompensationService,
        http_client: httpx.AsyncClient,
        task_queue: WorkflowTaskQueue,
        *,
        automation_service_base_url: str,
        publish_event: EventPublisher,
        approval_poll_interval_seconds: float,
        max_loop_iterations: int,
    ) -> None:
        self._instances = instances
        self._steps = steps
        self._results = results
        self._definitions = definitions
        self._versions = versions
        self._states = states
        self._logs = logs
        self._events = events
        self._approvals = approvals
        self._checkpoints = checkpoints
        self._compensations = compensations
        self._http_client = http_client
        self._task_queue = task_queue
        self._automation_service_base_url = automation_service_base_url
        self._publish_event = publish_event
        self._approval_poll_interval_seconds = approval_poll_interval_seconds
        self._max_loop_iterations = max_loop_iterations

    async def run_instance(
        self,
        instance_id: UUID,
        *,
        caller_token: str,
        seed_variables: dict[str, Any] | None = None,
    ) -> WorkflowInstance:
        """Run *instance_id* to completion, persisting every durable
        side effect along the way. *seed_variables* (a caller-supplied
        ``POST /workflows/{id}/execute`` body, or a parent instance's
        own resolved variables for a ``SUB_WORKFLOW``/``LOOP`` node)
        overlay *definition*'s own ``default_variables``.
        """
        instance = await self._instances.require_by_id(instance_id)
        definition = await self._definitions.get_by_id(instance.definition_id)
        version = await self._versions.get_by_id(instance.version_id)
        compiled = compile_version(definition, version)

        context = WorkflowContext(
            workflow_id=definition.workflow_key,
            execution_id=str(instance.id),
            organization_id=str(instance.organization_id),
            project_id=str(instance.project_id) if instance.project_id else None,
            user_id=str(instance.triggered_by) if instance.triggered_by else None,
        )
        for name, value in definition.default_variables.items():
            context.variables.set(name, value)
        for name, value in (seed_variables or {}).items():
            context.variables.set(name, value)

        await self._transition(instance, WorkflowInstanceStatus.RUNNING)
        instance.started_at = datetime.now(UTC)
        instance = await self._instances.update(instance)
        await self._publish_event(
            WorkflowStartedEvent(
                source_service="workflow-runtime-service",
                payload={"instance_id": str(instance.id), "workflow_id": definition.workflow_key},
            )
        )

        registry = self._build_handler_registry(instance, caller_token=caller_token)
        compensations = build_compensation_registry(instance, version, self._compensations)
        checkpoint_store = PersistentCheckpointStore()

        async def on_event(event: WorkflowEvent) -> None:
            await self._handle_sdk_event(instance, event)

        engine = WorkflowEngine(
            NodeExecutor(registry),
            compensations=compensations,
            checkpoints=checkpoint_store,
            on_event=on_event,
            source_service="workflow-runtime-service",
        )
        execution = await engine.run(compiled, context)

        for checkpoint in checkpoint_store.drain_pending():
            await self._checkpoints.persist(
                organization_id=instance.organization_id,
                instance_id=instance.id,
                checkpoint=checkpoint,
            )

        for node_id, node_result in execution.node_results.items():
            node_status = _NODE_STATUS_MAP.get(
                node_result.status.value, NodeExecutionStatus.PENDING
            )
            await self._steps.create(
                WorkflowExecutionStep(
                    organization_id=instance.organization_id,
                    instance_id=instance.id,
                    node_id=node_id,
                    node_type=compiled.graph.get_node(node_id).node_type,
                    status=node_status,
                    started_at=node_result.started_at,
                    finished_at=node_result.finished_at,
                    output=node_result.output,
                    error=node_result.error,
                    attempts=node_result.attempts,
                )
            )

        final_status = from_sdk_state(execution.status)
        await self._transition(instance, final_status)
        instance.finished_at = datetime.now(UTC)
        if final_status == WorkflowInstanceStatus.FAILED:
            failed = [
                result.error
                for result in execution.node_results.values()
                if result.error is not None
            ]
            instance.error_message = "; ".join(failed) if failed else None
        instance = await self._instances.update(instance)

        await self._results.create(
            WorkflowResult(
                organization_id=instance.organization_id,
                instance_id=instance.id,
                success=final_status == WorkflowInstanceStatus.COMPLETED,
                summary=f"Workflow instance ended in status {final_status.value!r}.",
                output={
                    node_id: result.output
                    for node_id, result in execution.node_results.items()
                    if result.output is not None
                },
                completed_at=instance.finished_at,
            )
        )
        event_cls = _TERMINAL_EVENTS.get(final_status)
        if event_cls is not None:
            await self._publish_event(
                event_cls(
                    source_service="workflow-runtime-service",
                    payload={"instance_id": str(instance.id)},
                )
            )
        return instance

    async def _transition(
        self, instance: WorkflowInstance, to_status: WorkflowInstanceStatus
    ) -> None:
        await self._states.record(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            from_status=instance.status,
            to_status=to_status,
        )
        instance.status = to_status

    async def _handle_sdk_event(self, instance: WorkflowInstance, event: WorkflowEvent) -> None:
        node_id = event.payload.get("node_id")
        if isinstance(event, TaskStartedEvent):
            message = f"Node {node_id} started."
        elif isinstance(event, TaskCompletedEvent):
            message = f"Node {node_id} completed."
        elif isinstance(event, TaskFailedEvent):
            message = f"Node {node_id} failed: {event.payload.get('error')}"
        else:
            message = event.event_name
        await self._logs.record(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            message=message,
            level="error" if isinstance(event, TaskFailedEvent) else "info",
            node_id=str(node_id) if node_id is not None else None,
        )
        await self._events.record(
            organization_id=instance.organization_id,
            instance_id=instance.id,
            event_type=event.event_name,
            payload=event.payload,
            occurred_at=event.timestamp,
        )

    def _build_handler_registry(
        self, instance: WorkflowInstance, *, caller_token: str
    ) -> NodeHandlerRegistry:
        registry = NodeHandlerRegistry()
        automation_client = AutomationClient(
            self._http_client,
            base_url=self._automation_service_base_url,
            caller_token=caller_token,
        )
        register_task_and_connector_handlers(registry, automation_client)
        register_approval_handlers(
            registry, self._approvals, poll_interval_seconds=self._approval_poll_interval_seconds
        )
        register_webhook_handler(registry, self._http_client)
        register_queue_handler(registry, self._task_queue)
        register_event_handler(registry, self._publish_event)

        async def trigger_sub_workflow(
            workflow_key: str, version_number: str | None, variables: dict[str, Any]
        ) -> dict[str, Any]:
            return await self._run_sub_workflow(
                instance, workflow_key, version_number, variables, caller_token=caller_token
            )

        register_subworkflow_and_loop_handlers(
            registry, trigger_sub_workflow, max_iterations=self._max_loop_iterations
        )
        return registry

    async def _run_sub_workflow(
        self,
        parent: WorkflowInstance,
        workflow_key: str,
        version_number: str | None,
        variables: dict[str, Any],
        *,
        caller_token: str,
    ) -> dict[str, Any]:
        child_definition = await self._definition_by_key(parent.organization_id, workflow_key)
        version = (
            await self._versions.get_by_id(UUID(version_number))
            if version_number
            else await self._versions.get_latest_for_definition(child_definition.id)
        )
        if version is None:
            raise ValueError(f"Sub-workflow {workflow_key!r} has no version yet.")
        child_instance = await self._instances.create(
            WorkflowInstance(
                organization_id=parent.organization_id,
                project_id=parent.project_id,
                definition_id=child_definition.id,
                version_id=version.id,
                parent_instance_id=parent.id,
                trigger_type=WorkflowTriggerType.EVENT,
                triggered_by=parent.triggered_by,
            )
        )
        finished = await self.run_instance(
            child_instance.id, caller_token=caller_token, seed_variables=variables
        )
        return {"instance_id": str(finished.id), "status": str(finished.status)}

    async def _definition_by_key(
        self, organization_id: UUID, workflow_key: str
    ) -> WorkflowDefinition:
        for definition in await self._definitions.list_for_org(organization_id):
            if definition.workflow_key == workflow_key:
                return definition
        raise ValueError(f"No workflow definition named {workflow_key!r} in this organization.")


__all__ = ["EventPublisher", "WorkflowExecutionService"]
