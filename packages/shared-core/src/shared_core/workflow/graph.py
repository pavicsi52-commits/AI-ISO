"""Workflow graph.

Per docs/028_Enterprise_Workflow_SDK.md.txt "DAG SUPPORT": the
underlying directed-graph data structure built from a workflow's
``NodeDefinition``/``EdgeDefinition`` lists -- adjacency lookups only;
cycle detection, topological ordering, and execution planning are
:mod:`shared_core.workflow.dag`'s own concern, built on top of this.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shared_core.workflow.edges import EdgeDefinition
from shared_core.workflow.exceptions import NodeNotFoundError
from shared_core.workflow.nodes import NodeDefinition, NodeType


@dataclass(slots=True)
class WorkflowGraph:
    """A workflow's nodes and edges, indexed for adjacency lookups."""

    nodes: dict[str, NodeDefinition] = field(default_factory=dict)
    edges: list[EdgeDefinition] = field(default_factory=list)

    def add_node(self, node: NodeDefinition) -> None:
        """Add *node* to the graph."""
        self.nodes[node.node_id] = node

    def add_edge(self, edge: EdgeDefinition) -> None:
        """Add *edge* to the graph.

        Raises:
            NodeNotFoundError: If either endpoint isn't a known node.
        """
        for node_id in (edge.from_node_id, edge.to_node_id):
            if node_id not in self.nodes:
                raise NodeNotFoundError(f"Edge references unknown node {node_id!r}.")
        self.edges.append(edge)

    def get_node(self, node_id: str) -> NodeDefinition:
        """Look up a node by id.

        Raises:
            NodeNotFoundError: If *node_id* isn't in the graph.
        """
        try:
            return self.nodes[node_id]
        except KeyError as exc:
            raise NodeNotFoundError(f"Node {node_id!r} is not in the graph.") from exc

    def successors(self, node_id: str) -> list[EdgeDefinition]:
        """Every outgoing edge from *node_id*."""
        return [edge for edge in self.edges if edge.from_node_id == node_id]

    def predecessors(self, node_id: str) -> list[EdgeDefinition]:
        """Every incoming edge to *node_id*."""
        return [edge for edge in self.edges if edge.to_node_id == node_id]

    def nodes_by_type(self, node_type: NodeType) -> list[NodeDefinition]:
        """Every node of *node_type*, in insertion order."""
        return [node for node in self.nodes.values() if node.node_type == node_type]


__all__ = ["WorkflowGraph"]
