"""Dependency, impact, and blast-radius analysis.

Three questions that look similar and are not:

- **Dependencies** -- "what does this need?" Follows dependency edges
  *outward*.
- **Impact** -- "what breaks if I change this?" Follows them *inward*.
- **Blast radius** -- "what breaks if this fails, and how badly?"
  Follows them inward too, but weights the answer by distance and edge
  strength, because a service three hops away behind a load balancer is
  not affected the way a database on the same host is.

**Direction is the whole distinction, and getting it backwards produces
a confident wrong answer** at exactly the moment an operator is relying
on it. That is why the direction is a named enum member at every call
site rather than a boolean.

**Cycles are expected, not exceptional.** Real estates contain
``A depends on B depends on A`` -- two services calling each other. The
traversal is breadth-first with a visited set, so a cycle terminates at
the first repeat instead of running to the depth ceiling.

**Nothing here is machine learning.** docs/049 "DO NOT IMPLEMENT" rules
it out, and none of these need it: they are graph traversals and
weighted sums with rules you can read.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from shared_core.enums.severity import Severity

from app.graph.entities import GraphNode, GraphRelationship, Subgraph
from app.graph.repository import GraphRepository
from app.models.enums import DEPENDENCY_TYPES, RelationshipType, TraversalDirection

DEFAULT_DEPTH = 3
"""How far analysis reaches by default.

Three hops covers application to host to rack in the common estate
shape. Deeper is available and bounded; deeper by *default* would make
every routine question expensive.
"""

DISTANCE_DECAY = 0.6
"""How much impact fades per hop.

A neighbour at distance 1 propagates at full edge weight; at distance 2
it is 0.6 of that, at 3 it is 0.36. The decay is what stops a blast
radius from reporting an entire data centre as equally affected because
everything is eventually connected to everything.
"""

_CRITICAL_THRESHOLD = 0.75
_HIGH_THRESHOLD = 0.5
_MEDIUM_THRESHOLD = 0.25


@dataclass(slots=True)
class AffectedNode:
    """One node reached by an analysis, with how hard it is hit."""

    node: GraphNode
    distance: int
    impact_score: float
    paths: int = 1
    """How many distinct routes reach this node.

    More routes means more ways to be affected, but it is reported
    rather than folded into the score: a node reachable by four paths is
    not four times as broken, and multiplying would say it was.
    """

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for an API response."""
        return {
            **self.node.as_dict(),
            "distance": self.distance,
            "impact_score": round(self.impact_score, 4),
            "paths": self.paths,
        }


@dataclass(slots=True)
class AnalysisResult:
    """The outcome of one dependency, impact, or blast-radius analysis."""

    root: GraphNode
    direction: TraversalDirection
    affected: list[AffectedNode] = field(default_factory=list)
    relationships: list[GraphRelationship] = field(default_factory=list)
    truncated: bool = False
    depth: int = DEFAULT_DEPTH

    @property
    def affected_count(self) -> int:
        """How many nodes the analysis reached, excluding the root."""
        return len(self.affected)

    @property
    def risk_score(self) -> float:
        """Overall risk, 0.0-1.0.

        The **maximum** single-node impact, not the sum. A sum grows
        with estate size, so a large healthy environment would score
        worse than a small fragile one -- the opposite of useful. The
        maximum answers "how badly is the worst-affected thing hit?",
        which is the question that decides whether to page someone.
        """
        if not self.affected:
            return 0.0
        return round(max(one.impact_score for one in self.affected), 4)

    @property
    def severity(self) -> Severity:
        """The platform severity band this risk score falls into."""
        score = self.risk_score
        if score >= _CRITICAL_THRESHOLD:
            return Severity.CRITICAL
        if score >= _HIGH_THRESHOLD:
            return Severity.HIGH
        if score >= _MEDIUM_THRESHOLD:
            return Severity.MEDIUM
        return Severity.LOW

    def by_type(self) -> dict[str, int]:
        """How many affected nodes of each type."""
        counts: dict[str, int] = {}
        for one in self.affected:
            counts[one.node.node_type] = counts.get(one.node.node_type, 0) + 1
        return counts

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for an API response."""
        return {
            "root": self.root.as_dict(),
            "direction": str(self.direction),
            "depth": self.depth,
            "affected": [one.as_dict() for one in self.affected],
            "affected_count": self.affected_count,
            "affected_by_type": self.by_type(),
            "relationships": [edge.as_dict() for edge in self.relationships],
            "risk_score": self.risk_score,
            "severity": str(self.severity),
            "truncated": self.truncated,
        }


class DependencyEngine:
    """Answers dependency, impact, and blast-radius questions."""

    def __init__(
        self,
        repository: GraphRepository,
        *,
        max_depth: int = 6,
        max_nodes: int = 5_000,
    ) -> None:
        self._repository = repository
        self._max_depth = max_depth
        self._max_nodes = max_nodes

    async def dependencies(
        self,
        organization_id: UUID,
        node_key: str,
        *,
        depth: int = DEFAULT_DEPTH,
        relationship_types: list[RelationshipType] | None = None,
    ) -> AnalysisResult:
        """What this node needs ("Dependency Lookup").

        Raises:
            NotFoundError: If the root node does not exist.
            ValidationError: If the traversal parameters are invalid.
        """
        return await self._analyse(
            organization_id,
            node_key,
            direction=TraversalDirection.OUTGOING,
            depth=depth,
            relationship_types=relationship_types,
        )

    async def impact(
        self,
        organization_id: UUID,
        node_key: str,
        *,
        depth: int = DEFAULT_DEPTH,
        relationship_types: list[RelationshipType] | None = None,
    ) -> AnalysisResult:
        """What breaks if this node changes ("IMPACT ANALYSIS").

        Raises:
            NotFoundError: If the root node does not exist.
            ValidationError: If the traversal parameters are invalid.
        """
        return await self._analyse(
            organization_id,
            node_key,
            direction=TraversalDirection.INCOMING,
            depth=depth,
            relationship_types=relationship_types,
        )

    async def blast_radius(
        self,
        organization_id: UUID,
        node_key: str,
        *,
        depth: int = DEFAULT_DEPTH,
        relationship_types: list[RelationshipType] | None = None,
    ) -> AnalysisResult:
        """What fails if this node fails ("BLAST RADIUS").

        The same inward traversal as :meth:`impact`; the difference is
        what a caller does with it. Kept as its own method because the
        two are asked at different moments -- impact before a change,
        blast radius during an incident -- and conflating them in the
        API would make the audit trail unable to tell them apart.

        Raises:
            NotFoundError: If the root node does not exist.
            ValidationError: If the traversal parameters are invalid.
        """
        return await self._analyse(
            organization_id,
            node_key,
            direction=TraversalDirection.INCOMING,
            depth=depth,
            relationship_types=relationship_types,
        )

    async def _analyse(
        self,
        organization_id: UUID,
        node_key: str,
        *,
        direction: TraversalDirection,
        depth: int,
        relationship_types: list[RelationshipType] | None,
    ) -> AnalysisResult:
        """Traverse once and score everything reached."""
        root = await self._repository.require_node(organization_id, node_key)
        types = relationship_types or sorted(DEPENDENCY_TYPES)
        subgraph = await self._repository.traverse(
            organization_id,
            node_key,
            direction=direction,
            relationship_types=types,
            depth=depth,
            limit=self._max_nodes,
        )
        result = AnalysisResult(
            root=root,
            direction=direction,
            relationships=subgraph.relationships,
            truncated=subgraph.truncated,
            depth=depth,
        )
        result.affected = score_affected(root_key=node_key, subgraph=subgraph, direction=direction)
        return result


def build_adjacency(
    subgraph: Subgraph, *, direction: TraversalDirection
) -> dict[str, list[tuple[str, float]]]:
    """Index a subgraph's edges for traversal in *direction*.

    For an inward analysis the adjacency is reversed, so walking
    "forward" through it is walking *towards* the dependents. Building
    it once turns the per-hop cost from a scan of every edge into a
    dictionary lookup.
    """
    adjacency: dict[str, list[tuple[str, float]]] = {}
    for edge in subgraph.relationships:
        weight = max(0.0, edge.weight)
        if direction is TraversalDirection.OUTGOING:
            adjacency.setdefault(edge.from_key, []).append((edge.to_key, weight))
        elif direction is TraversalDirection.INCOMING:
            adjacency.setdefault(edge.to_key, []).append((edge.from_key, weight))
        else:
            adjacency.setdefault(edge.from_key, []).append((edge.to_key, weight))
            adjacency.setdefault(edge.to_key, []).append((edge.from_key, weight))
    return adjacency


def score_affected(
    *, root_key: str, subgraph: Subgraph, direction: TraversalDirection
) -> list[AffectedNode]:
    """Score every node the traversal reached, by distance and weight.

    Breadth-first from the root, so the first time a node is reached is
    by its shortest path -- which is the route that propagates hardest.
    A ``visited`` set makes a cycle terminate at the first repeat rather
    than running to the depth ceiling.

    Returned strongest-first, because the top of the list is the part
    anyone reads.
    """
    nodes = {node.key: node for node in subgraph.nodes}
    adjacency = build_adjacency(subgraph, direction=direction)

    scores: dict[str, float] = {}
    distances: dict[str, int] = {}
    path_counts: dict[str, int] = {}
    visited: set[str] = {root_key}
    queue: deque[tuple[str, int, float]] = deque([(root_key, 0, 1.0)])

    while queue:
        current, distance, carried = queue.popleft()
        for neighbour, weight in adjacency.get(current, []):
            propagated = carried * weight * DISTANCE_DECAY
            path_counts[neighbour] = path_counts.get(neighbour, 0) + 1
            if neighbour in visited:
                # A second route to an already-scored node counts as
                # another path but does not re-score it: the shortest
                # route already carried the strongest propagation.
                continue
            visited.add(neighbour)
            distances[neighbour] = distance + 1
            scores[neighbour] = min(1.0, propagated)
            queue.append((neighbour, distance + 1, propagated))

    affected = [
        AffectedNode(
            node=nodes[key],
            distance=distances[key],
            impact_score=scores[key],
            paths=path_counts.get(key, 1),
        )
        for key in scores
        if key in nodes
    ]
    affected.sort(key=lambda one: (-one.impact_score, one.distance, one.node.key))
    return affected


def dependency_score(result: AnalysisResult) -> float:
    """How dependency-heavy a node is, 0.0-1.0 ("Dependency Scoring").

    Blends breadth (how many things) with proximity (how close), because
    neither alone describes a node well: something with two immediate
    dependencies is more fragile than something with twenty at four
    hops, and a plain count would rank them the other way round.
    """
    if not result.affected:
        return 0.0
    immediate = sum(1 for one in result.affected if one.distance == 1)
    breadth = min(1.0, len(result.affected) / 50.0)
    proximity = min(1.0, immediate / 10.0)
    return round((breadth * 0.4) + (proximity * 0.6), 4)


__all__ = [
    "DEFAULT_DEPTH",
    "DISTANCE_DECAY",
    "AffectedNode",
    "AnalysisResult",
    "DependencyEngine",
    "build_adjacency",
    "dependency_score",
    "score_affected",
]
