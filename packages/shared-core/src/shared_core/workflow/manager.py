"""Workflow manager.

Per docs/028_Enterprise_Workflow_SDK.md.txt "ACCEPTANCE CRITERIA"/
"WORKFLOW DEFINITION" ("Validate every workflow before execution."):
the top-level entry point tying registry, compilation, the engine, and
the runtime together -- one :class:`WorkflowManager` per service,
caching each registered (workflow id, version) pair's
:class:`~shared_core.workflow.compiler.CompiledWorkflow` so the same
version's graph and execution plan are computed once, not on every
execution ("DAG SUPPORT": Execution Planning). Nothing in this module
implements workflow behavior itself; it only wires together modules
that already do (``registry``, ``compiler``, ``engine``, ``runtime``,
``audit``).
"""

from __future__ import annotations

from shared_core.workflow import audit as workflow_audit
from shared_core.workflow.compiler import CompiledWorkflow, compile_workflow
from shared_core.workflow.context import WorkflowContext
from shared_core.workflow.definition import WorkflowDefinition
from shared_core.workflow.engine import WorkflowEngine
from shared_core.workflow.execution import WorkflowExecution
from shared_core.workflow.registry import WorkflowRegistry
from shared_core.workflow.runtime import WorkflowRuntime


class WorkflowManager:
    """Registers workflow definitions and runs executions of them."""

    def __init__(
        self,
        engine: WorkflowEngine,
        *,
        registry: WorkflowRegistry | None = None,
        runtime: WorkflowRuntime | None = None,
    ) -> None:
        self.registry = registry if registry is not None else WorkflowRegistry()
        self.runtime = runtime if runtime is not None else WorkflowRuntime(engine)
        self._compiled: dict[tuple[str, str], CompiledWorkflow] = {}

    def register_workflow(
        self, definition: WorkflowDefinition, *, actor_id: str | None = None
    ) -> CompiledWorkflow:
        """Validate, compile, and register *definition*.

        Enforces "Validate every workflow before execution".

        Raises:
            InvalidWorkflowDefinitionError: If *definition* is structurally invalid.
            CycleDetectedError: If *definition*'s graph contains a cycle.
        """
        is_update = self.registry.has(definition.workflow_id, version=definition.version)
        compiled = compile_workflow(definition)
        self.registry.register(definition)
        self._compiled[(definition.workflow_id, definition.version)] = compiled
        if is_update:
            workflow_audit.audit_workflow_updated(definition.workflow_id, actor_id=actor_id)
        else:
            workflow_audit.audit_workflow_created(definition.workflow_id, actor_id=actor_id)
        return compiled

    def delete_workflow(
        self, workflow_id: str, *, version: str | None = None, actor_id: str | None = None
    ) -> None:
        """Unregister a workflow, or just one *version* of it ("Workflow Deleted")."""
        versions = [version] if version is not None else self.registry.list_versions(workflow_id)
        for registered_version in versions:
            self._compiled.pop((workflow_id, registered_version), None)
        self.registry.unregister(workflow_id, version=version)
        workflow_audit.audit_workflow_deleted(workflow_id, actor_id=actor_id)

    def compiled_workflow(
        self, workflow_id: str, *, version: str | None = None
    ) -> CompiledWorkflow:
        """Return the cached :class:`CompiledWorkflow` for *workflow_id*, compiling on first use.

        Raises:
            WorkflowNotFoundError: If *workflow_id* (or that specific *version*) is not registered.
        """
        definition = self.registry.get(workflow_id, version=version)
        key = (definition.workflow_id, definition.version)
        compiled = self._compiled.get(key)
        if compiled is None:
            compiled = compile_workflow(definition)
            self._compiled[key] = compiled
        return compiled

    async def start_execution(
        self, workflow_id: str, context: WorkflowContext, *, version: str | None = None
    ) -> str:
        """Compile (if needed) and start running *workflow_id* in the background.

        Returns the execution id (``context.execution_id``), retrievable
        via :meth:`wait_execution`.

        Raises:
            WorkflowNotFoundError: If *workflow_id* (or that specific *version*) is not registered.
        """
        compiled = self.compiled_workflow(workflow_id, version=version)
        return await self.runtime.start(compiled, context)

    async def wait_execution(self, execution_id: str) -> WorkflowExecution:
        """Wait for *execution_id* to finish and return its final state."""
        return await self.runtime.wait(execution_id)

    def is_execution_running(self, execution_id: str) -> bool:
        """Whether *execution_id* is still in progress."""
        return self.runtime.is_running(execution_id)

    def cancel_execution(self, execution_id: str) -> None:
        """Cancel a running execution."""
        self.runtime.cancel(execution_id)

    def list_execution_ids(self) -> list[str]:
        """Every execution id the runtime is currently tracking."""
        return self.runtime.list_execution_ids()


__all__ = ["WorkflowManager"]
