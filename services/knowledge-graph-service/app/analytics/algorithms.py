"""Graph algorithms ("GRAPH ANALYTICS").

Degree and betweenness centrality, PageRank, community detection,
connected components, and the derived measures docs/049 names.

**These are implemented here, not delegated to Neo4j GDS.** The Graph
Data Science plugin is not present in Community Edition and is a
separate licensed product on Enterprise, so depending on it would mean
this service works on some Neo4j deployments and silently does not on
others. The edge set is pulled once and the computation runs in this
process, which is honest about where the cost lands and works on every
deployment the platform supports.

**That choice is what the node ceiling protects.** Betweenness is
O(V*E) -- on a hundred thousand nodes it would pin a core for minutes.
Every entry point checks the size first and refuses with the actual
number rather than accepting the request and timing out.

**None of this is machine learning.** docs/049 "DO NOT IMPLEMENT" rules
that out, and none of these need it: they are classical graph
algorithms with published definitions.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, cast

from shared_core.exceptions.validation import ValidationError

from app.graph.entities import Subgraph

DEFAULT_PAGERANK_ITERATIONS = 20
DEFAULT_DAMPING = 0.85
_TOP_N = 20

_MIN_NODES_FOR_BETWEENNESS = 3
"""Below three nodes there are no intermediaries, so every score is zero."""

_MIN_NODES_FOR_DENSITY = 2
"""Density is undefined for a single node -- there is no possible edge."""


@dataclass(slots=True)
class Graph:
    """An in-memory adjacency view of a subgraph.

    Built once and reused across algorithms, because every one of them
    starts by needing neighbours-of and the subgraph's edge list is the
    wrong shape for that.
    """

    nodes: list[str] = field(default_factory=list)
    outgoing: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    incoming: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    undirected: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    weights: dict[tuple[str, str], float] = field(default_factory=dict)

    @property
    def node_count(self) -> int:
        """How many nodes."""
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        """How many directed edges."""
        return sum(len(targets) for targets in self.outgoing.values())

    @classmethod
    def from_subgraph(cls, subgraph: Subgraph) -> Graph:
        """Index a subgraph for traversal.

        Nodes with no edges are kept. They score zero on every
        centrality measure, which is the correct answer and a different
        statement from "not present".
        """
        graph = cls(nodes=[node.key for node in subgraph.nodes])
        known = set(graph.nodes)
        for edge in subgraph.relationships:
            if edge.from_key not in known or edge.to_key not in known:
                # An edge to a node outside the subgraph would make
                # every measure disagree with the node list it is
                # reported against.
                continue
            graph.outgoing[edge.from_key].append(edge.to_key)
            graph.incoming[edge.to_key].append(edge.from_key)
            graph.undirected[edge.from_key].add(edge.to_key)
            graph.undirected[edge.to_key].add(edge.from_key)
            graph.weights[(edge.from_key, edge.to_key)] = max(0.0, edge.weight)
        return graph


def require_size(graph: Graph, *, ceiling: int) -> None:
    """Refuse a graph too large to analyse in reasonable time.

    Raises:
        ValidationError: If it exceeds *ceiling*, naming the actual
            size so the caller can narrow the scope rather than guess.
    """
    if graph.node_count > ceiling:
        raise ValidationError(
            f"This graph has {graph.node_count:,} nodes, above the "
            f"{ceiling:,}-node analytics ceiling. Narrow the scope by node "
            "type or project, or raise "
            "AIIOS_KNOWLEDGE_GRAPH_SERVICE_ANALYTICS_MAX_NODES."
        )


def degree_centrality(graph: Graph, *, normalise: bool = True) -> dict[str, float]:
    """How many neighbours each node has ("Degree Centrality").

    Normalised by the maximum possible degree, so a value is comparable
    between graphs of different sizes. Raw counts are available with
    *normalise* off, which is what a "how many things touch this?"
    question actually wants.
    """
    if graph.node_count == 0:
        return {}
    divisor = (graph.node_count - 1) if normalise and graph.node_count > 1 else 1
    return {node: len(graph.undirected.get(node, set())) / divisor for node in graph.nodes}


def in_degree(graph: Graph) -> dict[str, int]:
    """How many nodes depend on each node.

    The blunt version of impact: a node nothing points at cannot break
    anything else, whatever else is true of it.
    """
    return {node: len(graph.incoming.get(node, [])) for node in graph.nodes}


def out_degree(graph: Graph) -> dict[str, int]:
    """How many nodes each node depends on."""
    return {node: len(graph.outgoing.get(node, [])) for node in graph.nodes}


def betweenness_centrality(graph: Graph, *, normalise: bool = True) -> dict[str, float]:
    """How often each node sits on a shortest path ("Betweenness Centrality").

    Brandes' algorithm on the undirected view: one breadth-first sweep
    per node accumulating dependencies backwards, which is O(V*E) rather
    than the O(V^3) of computing all pairs first.

    This is the measure that finds **chokepoints** -- the switch every
    path crosses, which a degree count misses entirely because it has
    only two connections.
    """
    betweenness: dict[str, float] = dict.fromkeys(graph.nodes, 0.0)
    if graph.node_count < _MIN_NODES_FOR_BETWEENNESS:
        # With fewer than three nodes there are no intermediaries, so
        # every score is zero by definition rather than by computation.
        return betweenness

    for source in graph.nodes:
        stack: list[str] = []
        predecessors: dict[str, list[str]] = {node: [] for node in graph.nodes}
        sigma: dict[str, float] = dict.fromkeys(graph.nodes, 0.0)
        distance: dict[str, int] = dict.fromkeys(graph.nodes, -1)
        sigma[source] = 1.0
        distance[source] = 0
        queue: deque[str] = deque([source])

        while queue:
            current = queue.popleft()
            stack.append(current)
            for neighbour in graph.undirected.get(current, set()):
                if distance[neighbour] < 0:
                    distance[neighbour] = distance[current] + 1
                    queue.append(neighbour)
                if distance[neighbour] == distance[current] + 1:
                    sigma[neighbour] += sigma[current]
                    predecessors[neighbour].append(current)

        delta: dict[str, float] = dict.fromkeys(graph.nodes, 0.0)
        while stack:
            node = stack.pop()
            for predecessor in predecessors[node]:
                if sigma[node]:
                    delta[predecessor] += (sigma[predecessor] / sigma[node]) * (1 + delta[node])
            if node != source:
                betweenness[node] += delta[node]

    if normalise and graph.node_count >= _MIN_NODES_FOR_BETWEENNESS:
        # Each pair is counted from both ends on an undirected graph.
        scale = 2.0 / ((graph.node_count - 1) * (graph.node_count - 2))
        return {node: value * scale for node, value in betweenness.items()}
    return betweenness


def pagerank(
    graph: Graph,
    *,
    iterations: int = DEFAULT_PAGERANK_ITERATIONS,
    damping: float = DEFAULT_DAMPING,
    tolerance: float = 1e-6,
) -> dict[str, float]:
    """Importance by incoming links ("PageRank").

    Run on the **incoming** direction, so a node scores highly when many
    important things depend on it -- which is the infrastructure reading
    of importance. Running it on outgoing would rank the node with the
    most dependencies highest, which describes fragility, not criticality.

    Dangling nodes -- those with no outgoing edges -- have their rank
    redistributed across the graph rather than lost. Without that the
    ranks stop summing to 1 and the numbers become incomparable between
    runs.
    """
    count = graph.node_count
    if count == 0:
        return {}
    ranks = dict.fromkeys(graph.nodes, 1.0 / count)
    dangling = [node for node in graph.nodes if not graph.outgoing.get(node)]

    for _ in range(max(1, iterations)):
        leaked = sum(ranks[node] for node in dangling) / count
        updated: dict[str, float] = {}
        for node in graph.nodes:
            inbound = sum(
                ranks[source] / len(graph.outgoing[source])
                for source in graph.incoming.get(node, [])
                if graph.outgoing.get(source)
            )
            updated[node] = (1 - damping) / count + damping * (inbound + leaked)
        drift = sum(abs(updated[node] - ranks[node]) for node in graph.nodes)
        ranks = updated
        if drift < tolerance:
            # Converged. Continuing would burn iterations changing
            # nothing an operator could see.
            break
    return ranks


def connected_components(graph: Graph) -> list[list[str]]:
    """Groups of nodes reachable from each other ("Connected Components").

    More than one component in an estate graph usually means a
    synchronization gap rather than genuinely isolated infrastructure --
    which is why the count is surfaced in statistics.

    Returned largest-first, since the interesting question is what is
    *outside* the main component.
    """
    seen: set[str] = set()
    components: list[list[str]] = []
    for start in graph.nodes:
        if start in seen:
            continue
        component: list[str] = []
        queue: deque[str] = deque([start])
        seen.add(start)
        while queue:
            node = queue.popleft()
            component.append(node)
            for neighbour in graph.undirected.get(node, set()):
                if neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        components.append(sorted(component))
    components.sort(key=len, reverse=True)
    return components


def community_detection(graph: Graph, *, iterations: int = 10) -> dict[str, int]:
    """Group nodes into communities by label propagation ("Community Detection").

    Each node repeatedly adopts the most common label among its
    neighbours. Deterministic here -- nodes are processed in sorted
    order and ties break on the lowest label -- because the usual
    randomised form gives different communities on every run, and an
    operator comparing today's output to yesterday's needs them to mean
    the same thing.

    Communities are renumbered densely from 0 by descending size, so
    community 0 is always the largest.
    """
    labels = {node: index for index, node in enumerate(sorted(graph.nodes))}
    for _ in range(max(1, iterations)):
        changed = False
        for node in sorted(graph.nodes):
            neighbours = graph.undirected.get(node, set())
            if not neighbours:
                continue
            tally: dict[int, int] = defaultdict(int)
            for neighbour in neighbours:
                tally[labels[neighbour]] += 1
            best = min(
                sorted(tally.items(), key=lambda item: (-item[1], item[0]))[:1],
                default=None,
            )
            if best is not None and labels[node] != best[0]:
                labels[node] = best[0]
                changed = True
        if not changed:
            break

    sizes: dict[int, int] = defaultdict(int)
    for label in labels.values():
        sizes[label] += 1
    ordering = sorted(sizes.items(), key=lambda item: (-item[1], item[0]))
    renumbered = {label: index for index, (label, _size) in enumerate(ordering)}
    return {node: renumbered[label] for node, label in labels.items()}


def relationship_density(graph: Graph) -> float:
    """How connected the graph is, 0.0-1.0 ("Relationship Density").

    Edges as a fraction of the maximum possible for that node count.
    Real infrastructure graphs are sparse -- a density above roughly
    0.1 usually means the estate is small rather than that everything
    is genuinely connected to everything.
    """
    count = graph.node_count
    if count < _MIN_NODES_FOR_DENSITY:
        return 0.0
    possible = count * (count - 1)
    return round(graph.edge_count / possible, 6)


def critical_assets(
    graph: Graph,
    *,
    criticality: dict[str, float] | None = None,
    limit: int = _TOP_N,
) -> list[dict[str, Any]]:
    """The nodes whose loss would hurt most ("Critical Asset Identification").

    Blends three signals, because each alone is wrong in a way the
    others correct:

    - **PageRank** -- important things depend on it.
    - **Betweenness** -- it is a chokepoint, which a two-connection
      switch is and no degree count would show.
    - **Operator-declared criticality** -- a node can be structurally
      peripheral and still be the one thing the business cannot lose.
      Nothing computed from topology can know that, which is why it is
      declared rather than derived.
    """
    if graph.node_count == 0:
        return []
    declared = criticality or {}
    ranks = pagerank(graph)
    between = betweenness_centrality(graph)
    degrees = degree_centrality(graph)

    max_rank = max(ranks.values(), default=0.0) or 1.0
    max_between = max(between.values(), default=0.0) or 1.0

    scored = [
        {
            "key": node,
            "score": round(
                0.4 * (ranks.get(node, 0.0) / max_rank)
                + 0.3 * (between.get(node, 0.0) / max_between)
                + 0.3 * declared.get(node, 0.0),
                4,
            ),
            "pagerank": round(ranks.get(node, 0.0), 6),
            "betweenness": round(between.get(node, 0.0), 6),
            "degree": round(degrees.get(node, 0.0), 4),
            "declared_criticality": declared.get(node, 0.0),
        }
        for node in graph.nodes
    ]

    # The score is written as a float two lines above; the cast is for
    # the type checker, which only sees dict[str, Any] here.
    def _order(item: dict[str, Any]) -> tuple[float, str]:
        return (-float(cast(float, item["score"])), str(item["key"]))

    scored.sort(key=_order)
    return scored[:limit]


def risk_propagation(
    graph: Graph,
    *,
    failed_keys: list[str],
    decay: float = 0.6,
    max_depth: int = 5,
) -> dict[str, float]:
    """Spread risk outward from failed nodes ("Risk Propagation").

    Breadth-first from every failed node at once, following *incoming*
    edges -- the direction dependents lie in. A node reachable from two
    failures takes the higher of the two risks rather than their sum:
    something already fully broken by one failure is not more broken by
    a second.
    """
    risk: dict[str, float] = {}
    queue: deque[tuple[str, int, float]] = deque()
    for key in failed_keys:
        if key in graph.undirected or key in graph.nodes:
            risk[key] = 1.0
            queue.append((key, 0, 1.0))

    while queue:
        current, depth, carried = queue.popleft()
        if depth >= max_depth:
            continue
        for dependent in graph.incoming.get(current, []):
            weight = graph.weights.get((dependent, current), 1.0)
            propagated = carried * decay * max(0.0, min(1.0, weight))
            if propagated <= risk.get(dependent, 0.0):
                continue
            risk[dependent] = round(propagated, 6)
            queue.append((dependent, depth + 1, propagated))
    return risk


def shortest_path_length(graph: Graph, *, source: str, target: str) -> int | None:
    """Hops between two nodes, or ``None`` if they are not connected.

    ``None`` rather than infinity or -1: "these are not connected" is a
    real answer, and a sentinel number invites arithmetic on it.
    """
    if source == target:
        return 0
    if source not in graph.undirected and source not in graph.nodes:
        return None
    seen = {source}
    queue: deque[tuple[str, int]] = deque([(source, 0)])
    while queue:
        node, distance = queue.popleft()
        for neighbour in graph.undirected.get(node, set()):
            if neighbour == target:
                return distance + 1
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append((neighbour, distance + 1))
    return None


__all__ = [
    "DEFAULT_DAMPING",
    "DEFAULT_PAGERANK_ITERATIONS",
    "Graph",
    "betweenness_centrality",
    "community_detection",
    "connected_components",
    "critical_assets",
    "degree_centrality",
    "in_degree",
    "out_degree",
    "pagerank",
    "relationship_density",
    "require_size",
    "risk_propagation",
    "shortest_path_length",
]
