"""DAG validation and execution planning.

Per docs/028_Enterprise_Workflow_SDK.md.txt "DAG SUPPORT": Directed
Acyclic Graph, Dependency Validation, Cycle Detection, Topological
Ordering, Execution Planning.
"""

from __future__ import annotations

from shared_core.workflow.exceptions import CycleDetectedError
from shared_core.workflow.graph import WorkflowGraph

_UNVISITED = 0
_VISITING = 1
_VISITED = 2


def detect_cycle(graph: WorkflowGraph) -> list[str] | None:
    """Detect a cycle in *graph* via depth-first search ("Cycle Detection").

    Returns the cycle's node ids (in traversal order) if one exists, else ``None``.
    """
    color: dict[str, int] = dict.fromkeys(graph.nodes, _UNVISITED)
    path: list[str] = []

    def visit(node_id: str) -> list[str] | None:
        color[node_id] = _VISITING
        path.append(node_id)
        for edge in graph.successors(node_id):
            neighbor = edge.to_node_id
            neighbor_color = color.get(neighbor, _UNVISITED)
            if neighbor_color == _VISITING:
                cycle_start = path.index(neighbor)
                return [*path[cycle_start:], neighbor]
            if neighbor_color == _UNVISITED:
                found = visit(neighbor)
                if found is not None:
                    return found
        path.pop()
        color[node_id] = _VISITED
        return None

    for node_id in list(graph.nodes):
        if color[node_id] == _UNVISITED:
            found = visit(node_id)
            if found is not None:
                return found
    return None


def validate_dag(graph: WorkflowGraph) -> None:
    """Validate *graph* is a genuine DAG ("Dependency Validation").

    Raises:
        CycleDetectedError: If a cycle is found.
    """
    cycle = detect_cycle(graph)
    if cycle is not None:
        raise CycleDetectedError(f"Cycle detected: {' -> '.join(cycle)}.")


def topological_order(graph: WorkflowGraph) -> list[str]:
    """Return every node id in a valid topological order ("Topological Ordering").

    Raises:
        CycleDetectedError: If *graph* isn't a valid DAG.
    """
    validate_dag(graph)
    in_degree = dict.fromkeys(graph.nodes, 0)
    for edge in graph.edges:
        in_degree[edge.to_node_id] += 1

    ready = [node_id for node_id, degree in in_degree.items() if degree == 0]
    ordered: list[str] = []
    while ready:
        node_id = ready.pop(0)
        ordered.append(node_id)
        for edge in graph.successors(node_id):
            in_degree[edge.to_node_id] -= 1
            if in_degree[edge.to_node_id] == 0:
                ready.append(edge.to_node_id)
    return ordered


def execution_plan(graph: WorkflowGraph) -> list[list[str]]:
    """Group nodes into ordered "levels" that can each run in parallel ("Execution Planning").

    Every node in one level has all its dependencies satisfied by
    nodes in strictly earlier levels -- consumed directly by
    :mod:`shared_core.workflow.parallel` to decide what's safe to run
    concurrently.

    Raises:
        CycleDetectedError: If *graph* isn't a valid DAG.
    """
    validate_dag(graph)
    in_degree = dict.fromkeys(graph.nodes, 0)
    for edge in graph.edges:
        in_degree[edge.to_node_id] += 1

    remaining = set(graph.nodes)
    levels: list[list[str]] = []
    while remaining:
        level = sorted(node_id for node_id in remaining if in_degree[node_id] == 0)
        if not level:
            # validate_dag already ruled this out; guards against a logic
            # bug here from ever hanging in an infinite loop.
            raise CycleDetectedError("Execution planning could not make progress.")
        levels.append(level)
        remaining -= set(level)
        for node_id in level:
            for edge in graph.successors(node_id):
                in_degree[edge.to_node_id] -= 1
    return levels


__all__ = ["detect_cycle", "execution_plan", "topological_order", "validate_dag"]
