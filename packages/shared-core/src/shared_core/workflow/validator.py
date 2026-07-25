"""Workflow definition validation.

Per docs/028_Enterprise_Workflow_SDK.md.txt "WORKFLOW DEFINITION":
"Validate every workflow before execution." Structural validation of a
:class:`~shared_core.workflow.definition.WorkflowDefinition` -- unique
node ids, exactly one ``START`` node, at least one ``END`` node, every
node reachable from ``START``, and (via
:mod:`shared_core.workflow.dag`) that the graph is a genuine DAG.
"""

from __future__ import annotations

from shared_core.workflow.dag import validate_dag
from shared_core.workflow.definition import WorkflowDefinition
from shared_core.workflow.exceptions import InvalidWorkflowDefinitionError
from shared_core.workflow.graph import WorkflowGraph
from shared_core.workflow.nodes import NodeType


def build_graph(definition: WorkflowDefinition) -> WorkflowGraph:
    """Build a :class:`WorkflowGraph` from *definition*'s nodes and edges."""
    graph = WorkflowGraph()
    for node in definition.nodes:
        graph.add_node(node)
    for edge in definition.edges:
        graph.add_edge(edge)
    return graph


def validate_definition(definition: WorkflowDefinition) -> WorkflowGraph:
    """Validate *definition* is structurally sound and return its compiled graph.

    Raises:
        InvalidWorkflowDefinitionError: If node ids aren't unique,
            there isn't exactly one ``START`` node, there's no ``END``
            node, or some node is unreachable from ``START``.
        CycleDetectedError: If the graph contains a cycle.
    """
    node_ids = [node.node_id for node in definition.nodes]
    if len(node_ids) != len(set(node_ids)):
        raise InvalidWorkflowDefinitionError("Workflow node ids must be unique.")

    graph = build_graph(definition)

    start_nodes = graph.nodes_by_type(NodeType.START)
    if len(start_nodes) != 1:
        raise InvalidWorkflowDefinitionError(
            f"A workflow must have exactly one START node; found {len(start_nodes)}."
        )
    if not graph.nodes_by_type(NodeType.END):
        raise InvalidWorkflowDefinitionError("A workflow must have at least one END node.")

    validate_dag(graph)
    _validate_reachability(graph, start_nodes[0].node_id)
    return graph


def _validate_reachability(graph: WorkflowGraph, start_node_id: str) -> None:
    reachable = {start_node_id}
    frontier = [start_node_id]
    while frontier:
        node_id = frontier.pop()
        for edge in graph.successors(node_id):
            if edge.to_node_id not in reachable:
                reachable.add(edge.to_node_id)
                frontier.append(edge.to_node_id)
    unreachable = set(graph.nodes) - reachable
    if unreachable:
        raise InvalidWorkflowDefinitionError(
            f"Unreachable node(s) from START: {sorted(unreachable)}."
        )


__all__ = ["build_graph", "validate_definition"]
