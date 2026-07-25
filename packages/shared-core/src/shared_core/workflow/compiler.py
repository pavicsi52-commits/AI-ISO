"""Workflow compilation.

Per docs/028_Enterprise_Workflow_SDK.md.txt "DAG SUPPORT": Execution
Planning. Turns a :class:`~shared_core.workflow.definition.WorkflowDefinition`
into a :class:`CompiledWorkflow` -- its validated graph plus a
precomputed execution plan (topological levels) -- so the runtime
never recomputes graph structure on every single execution of the same
workflow version.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared_core.workflow.dag import execution_plan as compute_execution_plan
from shared_core.workflow.definition import WorkflowDefinition
from shared_core.workflow.graph import WorkflowGraph
from shared_core.workflow.validator import validate_definition


@dataclass(frozen=True, slots=True)
class CompiledWorkflow:
    """A validated :class:`WorkflowDefinition` plus its precomputed execution plan."""

    definition: WorkflowDefinition
    graph: WorkflowGraph
    execution_plan: list[list[str]]


def compile_workflow(definition: WorkflowDefinition) -> CompiledWorkflow:
    """Validate *definition* and compile it into a :class:`CompiledWorkflow`.

    Raises:
        InvalidWorkflowDefinitionError: If *definition* is structurally invalid.
        CycleDetectedError: If *definition*'s graph contains a cycle.
    """
    graph = validate_definition(definition)
    plan = compute_execution_plan(graph)
    return CompiledWorkflow(definition=definition, graph=graph, execution_plan=plan)


__all__ = ["CompiledWorkflow", "compile_workflow"]
