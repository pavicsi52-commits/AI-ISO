"""Topology visualisation over Neo4j ("TOPOLOGY VISUALIZATION").

Integrates Prompt 036's graph rather than re-deriving relationships:
the inventory service owns what is connected to what, and this service
only asks the questions a picture needs answering.

**Traversals are bounded twice -- by depth and by node count.** Graph
traversal grows exponentially, and an unbounded blast-radius query on a
large estate is an outage, not a visualisation. Hitting the node
ceiling returns a *truncated* graph flagged as such, so a viewer knows
they are looking at a partial picture rather than a complete one that
happens to be small.

**Every query is parameterised.** Node ids, labels, and depths arrive
from user-authored widget definitions, so building Cypher by string
concatenation would be an injection path straight into the graph.
Depth cannot be parameterised in a Cypher range literal, so it is
validated as an integer against a hard ceiling before interpolation --
the one place a value is formatted into the query text, and the reason
that validation is not optional.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared_core.exceptions.dependency import DependencyError
from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.models.enums import TopologyQueryKind

logger = get_logger("app.topology.graph")

MAX_DEPTH_CEILING = 10
"""Hard upper bound on traversal depth, regardless of configuration."""


@dataclass(frozen=True, slots=True)
class GraphNode:
    """One node in a rendered topology."""

    id: str
    label: str
    kind: str
    properties: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for a widget payload."""
        return {
            "id": self.id,
            "label": self.label,
            "kind": self.kind,
            "properties": self.properties,
        }


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """One directed relationship between two nodes."""

    source: str
    target: str
    kind: str
    properties: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for a widget payload."""
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "properties": self.properties,
        }


@dataclass(slots=True)
class TopologyGraph:
    """A rendered topology, ready for a widget payload."""

    root_id: str
    kind: TopologyQueryKind
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    truncated: bool = False

    @property
    def node_count(self) -> int:
        """How many nodes the graph carries."""
        return len(self.nodes)

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for a widget payload."""
        return {
            "root_id": self.root_id,
            "kind": str(self.kind),
            "nodes": [node.as_dict() for node in self.nodes],
            "edges": [edge.as_dict() for edge in self.edges],
            "truncated": self.truncated,
            "node_count": self.node_count,
            "edge_count": len(self.edges),
        }


_DIRECTION: dict[TopologyQueryKind, str] = {
    TopologyQueryKind.NEIGHBORS: "-[r*1..{depth}]-",
    TopologyQueryKind.DEPENDENCIES: "-[r:DEPENDS_ON*1..{depth}]->",
    TopologyQueryKind.DEPENDENTS: "<-[r:DEPENDS_ON*1..{depth}]-",
    TopologyQueryKind.BLAST_RADIUS: "<-[r:DEPENDS_ON|RUNS_ON|CONNECTS_TO*1..{depth}]-",
    TopologyQueryKind.SERVICE_MAP: "-[r:PROVIDES|CONSUMES*1..{depth}]-",
    TopologyQueryKind.CLUSTER_MAP: "-[r:MEMBER_OF|HOSTS*1..{depth}]-",
    TopologyQueryKind.APPLICATION_TOPOLOGY: "-[r:RUNS_ON|DEPENDS_ON|PROVIDES*1..{depth}]-",
}
"""Relationship pattern per query kind.

Direction is the whole point of the distinction: *dependencies* follows
``DEPENDS_ON`` outward ("what do I need?"), while *dependents* and
*blast radius* follow it inward ("who breaks if I go down?"). Getting
that backwards would produce a confident, wrong answer to the question
an operator most needs during an incident.
"""


def validate_depth(depth: int, *, ceiling: int) -> int:
    """Validate a traversal depth before it reaches a Cypher literal.

    Raises:
        ValidationError: If the depth is not a positive integer within
            the configured ceiling. This is the single place a value is
            interpolated into query text, so the check is what keeps
            that safe.
    """
    if isinstance(depth, bool) or not isinstance(depth, int):
        raise ValidationError(f"Traversal depth must be an integer, got {depth!r}.")
    limit = min(ceiling, MAX_DEPTH_CEILING)
    if depth < 1 or depth > limit:
        raise ValidationError(f"Traversal depth must be between 1 and {limit}, got {depth}.")
    return depth


def build_cypher(kind: TopologyQueryKind, depth: int, *, ceiling: int) -> str:
    """Build the parameterised Cypher for one traversal.

    Only ``depth`` is interpolated, and only after
    :func:`validate_depth` has proven it a bounded integer. Everything
    else -- the root id, the organization, the node limit -- is a real
    query parameter.

    Raises:
        ValidationError: If the kind is unsupported or depth invalid.
    """
    pattern = _DIRECTION.get(kind)
    if pattern is None:
        supported = ", ".join(sorted(str(member) for member in _DIRECTION))
        raise ValidationError(
            f"Topology query kind {str(kind)!r} is not supported. Supported: {supported}."
        )
    safe_depth = validate_depth(depth, ceiling=ceiling)
    return (
        "MATCH (root {id: $root_id, organization_id: $organization_id}) "
        f"MATCH path = (root){pattern.format(depth=safe_depth)}(other) "
        "WITH root, other, relationships(path) AS rels "
        "UNWIND rels AS rel "
        "RETURN DISTINCT "
        "  root.id AS root_id, "
        "  other.id AS other_id, "
        "  labels(other) AS other_labels, "
        "  coalesce(other.name, other.id) AS other_name, "
        "  properties(other) AS other_props, "
        "  startNode(rel).id AS rel_source, "
        "  endNode(rel).id AS rel_target, "
        "  type(rel) AS rel_type "
        "LIMIT $max_nodes"
    )


def build_graph(
    root_id: str, kind: TopologyQueryKind, records: list[dict[str, Any]], *, max_nodes: int
) -> TopologyGraph:
    """Assemble query records into a de-duplicated graph.

    Neo4j returns one row per relationship, so the same node appears
    many times; nodes and edges are both de-duplicated here rather than
    shipping a payload where a single host is drawn eight times.
    """
    graph = TopologyGraph(root_id=root_id, kind=kind)
    seen_nodes: dict[str, GraphNode] = {}
    seen_edges: set[tuple[str, str, str]] = set()

    for record in records:
        other_id = record.get("other_id")
        if other_id and other_id not in seen_nodes:
            labels = record.get("other_labels") or []
            seen_nodes[str(other_id)] = GraphNode(
                id=str(other_id),
                label=str(record.get("other_name") or other_id),
                kind=str(labels[0]) if labels else "Node",
                properties=dict(record.get("other_props") or {}),
            )
        source, target = record.get("rel_source"), record.get("rel_target")
        rel_type = str(record.get("rel_type") or "RELATED")
        if source and target:
            signature = (str(source), str(target), rel_type)
            if signature not in seen_edges:
                seen_edges.add(signature)
                graph.edges.append(
                    GraphEdge(source=str(source), target=str(target), kind=rel_type)
                )

    if root_id not in seen_nodes:
        seen_nodes[root_id] = GraphNode(id=root_id, label=root_id, kind="Root")
    graph.nodes = list(seen_nodes.values())
    graph.truncated = len(records) >= max_nodes
    if graph.truncated:
        logger.warning(
            "Topology query hit the node ceiling; returning a truncated graph.",
            extra={"extra_fields": {"root_id": root_id, "max_nodes": max_nodes}},
        )
    return graph


class TopologyReader:
    """Reads topology from Neo4j for dashboard widgets."""

    def __init__(
        self,
        driver: Any,
        *,
        database: str = "neo4j",
        max_depth: int = 4,
        max_nodes: int = 500,
        enabled: bool = True,
    ) -> None:
        self._driver = driver
        self._database = database
        self._max_depth = max_depth
        self._max_nodes = max_nodes
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        """Whether topology is configured on this deployment."""
        return self._enabled and self._driver is not None

    async def query(
        self,
        *,
        organization_id: str,
        root_id: str,
        kind: TopologyQueryKind = TopologyQueryKind.NEIGHBORS,
        depth: int = 2,
    ) -> TopologyGraph:
        """Run one traversal and assemble the graph.

        Raises:
            ValidationError: If the query parameters are invalid.
            DependencyError: If topology is unconfigured or Neo4j is
                unreachable. The widget resolver catches this and marks
                the widget failed rather than failing the dashboard.
        """
        if not self.enabled:
            raise DependencyError("Topology visualisation is not configured on this deployment.")
        if not root_id:
            raise ValidationError("A topology query requires a root node id.")

        cypher = build_cypher(kind, depth, ceiling=self._max_depth)
        try:
            async with self._driver.session(database=self._database) as session:
                result = await session.run(
                    cypher,
                    root_id=root_id,
                    organization_id=organization_id,
                    max_nodes=self._max_nodes,
                )
                records = [dict(record) async for record in result]
        except Exception as exc:
            logger.warning(
                "Topology query failed.",
                extra={"extra_fields": {"root_id": root_id, "error": str(exc)}},
            )
            raise DependencyError(f"Topology query failed: {exc}") from exc

        return build_graph(root_id, kind, records, max_nodes=self._max_nodes)


__all__ = [
    "MAX_DEPTH_CEILING",
    "GraphEdge",
    "GraphNode",
    "TopologyGraph",
    "TopologyReader",
    "build_cypher",
    "build_graph",
    "validate_depth",
]
