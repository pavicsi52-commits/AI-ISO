"""Enterprise Workflow SDK factory.

Assembles the executor, engine, runtime, and registry into one
:class:`~shared_core.workflow.manager.WorkflowManager` a service builds
exactly once at startup -- mirroring
:func:`shared_core.scheduler.factory.create_scheduler_framework`
(Prompt 026). Takes an already-configured
:class:`~shared_core.workflow.executor.NodeHandlerRegistry` rather than
building one, since only the calling service knows what its
business-specific node types (``TASK``/``CONNECTOR``/``PLUGIN``/``AI``/
...) actually do, per docs/028 "DO NOT IMPLEMENT".
"""

from __future__ import annotations

from opentelemetry.trace import Tracer

from shared_core.queue.retry import RetryPolicy
from shared_core.workflow.checkpoint import CheckpointStore
from shared_core.workflow.compensation import CompensationRegistry
from shared_core.workflow.constants import DEFAULT_SOURCE_SERVICE
from shared_core.workflow.engine import EventHandler, WorkflowEngine
from shared_core.workflow.executor import NodeExecutor, NodeHandlerRegistry
from shared_core.workflow.manager import WorkflowManager
from shared_core.workflow.registry import WorkflowRegistry
from shared_core.workflow.runtime import WorkflowRuntime


def create_workflow_framework(
    handlers: NodeHandlerRegistry,
    *,
    tracer: Tracer | None = None,
    on_event: EventHandler | None = None,
    retry_policy: RetryPolicy | None = None,
    compensations: CompensationRegistry | None = None,
    checkpoints: CheckpointStore | None = None,
    source_service: str = DEFAULT_SOURCE_SERVICE,
) -> WorkflowManager:
    """Build a fully-wired :class:`WorkflowManager` from a caller-configured handler registry."""
    executor = NodeExecutor(handlers)
    engine = WorkflowEngine(
        executor,
        compensations=compensations,
        checkpoints=checkpoints,
        tracer=tracer,
        on_event=on_event,
        source_service=source_service,
        retry_policy=retry_policy,
    )
    return WorkflowManager(engine, registry=WorkflowRegistry(), runtime=WorkflowRuntime(engine))


__all__ = ["create_workflow_framework"]
