"""Graph analytics and analysis, as a service ("GRAPH ANALYTICS").

Wraps the pure algorithms in :mod:`app.analytics.algorithms` and the
traversals in :mod:`app.dependencies.engine` with the parts that need
the database: reading the graph, enriching results with declared
criticality, publishing events, and storing the analysis.

**Analyses are stored because they are quoted later.** An impact or
blast-radius number turns up in an incident review hours after the
graph has moved on. Persisting the result with the parameters that
produced it means the figure in the review is the one the tool
produced, not one someone re-derived against a different graph.

**The whole graph is pulled once per analytics request.** The algorithms
run in this process rather than in Neo4j GDS -- absent on Community,
separately licensed on Enterprise -- so the node ceiling is what keeps
that honest. Above it the request is refused with the actual size
rather than accepted and left to time out.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.exceptions.validation import ValidationError
from shared_core.logging.logger import get_logger

from app.analytics.algorithms import (
    Graph,
    betweenness_centrality,
    community_detection,
    connected_components,
    critical_assets,
    degree_centrality,
    in_degree,
    out_degree,
    pagerank,
    relationship_density,
    require_size,
    risk_propagation,
    shortest_path_length,
)
from app.cypher.builder import MAX_LIMIT_CEILING
from app.dependencies.engine import AnalysisResult, DependencyEngine, dependency_score
from app.events.graph_events import (
    SOURCE_SERVICE,
    BlastRadiusCalculatedEvent,
    ImpactAnalysisCompletedEvent,
)
from app.graph.repository import GraphRepository
from app.models.enums import AnalyticsAlgorithm, QueryKind, RelationshipType
from app.models.graph_report import GraphReport
from app.repositories.graph_metadata import GraphMetadataRepository
from app.repositories.graph_report import GraphReportRepository
from app.types import EventPublisher

logger = get_logger("app.services.analytics")

_TOP_N = 20


_Computed = tuple[dict[str, Any], list[dict[str, Any]]]
"""What every algorithm handler returns: ``(values, ranked)``."""


@dataclass(slots=True)
class AnalyticsOutcome:
    """The result of one analytics computation."""

    algorithm: AnalyticsAlgorithm
    values: dict[str, Any] = field(default_factory=dict)
    ranked: list[dict[str, Any]] = field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0
    duration_ms: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        """JSON-serialisable form for an API response."""
        return {
            "algorithm": str(self.algorithm),
            "values": self.values,
            "ranked": self.ranked,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "duration_ms": round(self.duration_ms, 2),
        }


class AnalyticsService:
    """Runs graph algorithms and dependency analyses."""

    def __init__(
        self,
        graph: GraphRepository,
        reports: GraphReportRepository,
        metadata: GraphMetadataRepository,
        dependencies: DependencyEngine,
        *,
        publish_event: EventPublisher,
        max_nodes: int = MAX_LIMIT_CEILING,
        pagerank_iterations: int = 20,
        pagerank_damping: float = 0.85,
    ) -> None:
        self._graph = graph
        self._reports = reports
        self._metadata = metadata
        self._dependencies = dependencies
        self._publish_event = publish_event
        self._max_nodes = max_nodes
        self._iterations = pagerank_iterations
        self._damping = pagerank_damping

    # ---- dependency analyses ---------------------------------------

    async def dependencies(
        self,
        organization_id: UUID,
        node_key: str,
        *,
        depth: int = 3,
        relationship_types: list[RelationshipType] | None = None,
        store: bool = False,
        actor_id: UUID | None = None,
    ) -> AnalysisResult:
        """What this node needs.

        Raises:
            NotFoundError: If the root does not exist.
            ValidationError: If the traversal parameters are invalid.
        """
        result = await self._dependencies.dependencies(
            organization_id, node_key, depth=depth, relationship_types=relationship_types
        )
        if store:
            await self._store(
                organization_id,
                result,
                kind=QueryKind.DEPENDENCY_LOOKUP,
                title=f"Dependencies of {node_key}",
                actor_id=actor_id,
            )
        return result

    async def impact(
        self,
        organization_id: UUID,
        node_key: str,
        *,
        depth: int = 3,
        relationship_types: list[RelationshipType] | None = None,
        store: bool = True,
        actor_id: UUID | None = None,
    ) -> AnalysisResult:
        """What breaks if this node changes ("IMPACT ANALYSIS").

        Stored by default, unlike a dependency lookup: an impact number
        is the kind that gets quoted in a change review.
        """
        result = await self._dependencies.impact(
            organization_id, node_key, depth=depth, relationship_types=relationship_types
        )
        if store:
            await self._store(
                organization_id,
                result,
                kind=QueryKind.IMPACT_ANALYSIS,
                title=f"Impact of changing {node_key}",
                actor_id=actor_id,
            )
        await self._publish_event(
            ImpactAnalysisCompletedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "node_key": node_key,
                    "affected_count": result.affected_count,
                    "severity": str(result.severity),
                },
            )
        )
        return result

    async def blast_radius(
        self,
        organization_id: UUID,
        node_key: str,
        *,
        depth: int = 3,
        relationship_types: list[RelationshipType] | None = None,
        store: bool = True,
        actor_id: UUID | None = None,
    ) -> AnalysisResult:
        """What fails if this node fails ("BLAST RADIUS")."""
        result = await self._dependencies.blast_radius(
            organization_id, node_key, depth=depth, relationship_types=relationship_types
        )
        if store:
            await self._store(
                organization_id,
                result,
                kind=QueryKind.BLAST_RADIUS,
                title=f"Blast radius of {node_key}",
                actor_id=actor_id,
            )
        await self._publish_event(
            BlastRadiusCalculatedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "node_key": node_key,
                    "affected_count": result.affected_count,
                    "risk_score": result.risk_score,
                    "severity": str(result.severity),
                },
            )
        )
        return result

    # ---- algorithms -------------------------------------------------

    async def run(
        self,
        organization_id: UUID,
        algorithm: AnalyticsAlgorithm,
        *,
        parameters: dict[str, Any] | None = None,
    ) -> AnalyticsOutcome:
        """Run one graph algorithm over the organization's graph.

        Raises:
            ValidationError: If the algorithm is unknown, the graph
                exceeds the analytics ceiling, or a required parameter
                is missing.
            DependencyError: If the graph is unreachable.
        """
        started = time.monotonic()
        # Counted before loading, never after. ``_load`` reads with
        # ``LIMIT max_nodes``, so an oversized graph comes back
        # *truncated* -- and ``require_size``, which can only see what
        # was loaded, would then wave it through. The analysis would run
        # on part of the estate and report confident centrality and
        # component numbers for a graph that is not the one in the
        # database, which is worse than refusing.
        await self._require_analysable(organization_id)
        graph = await self._load(organization_id)
        require_size(graph, ceiling=self._max_nodes)

        outcome = AnalyticsOutcome(
            algorithm=algorithm,
            node_count=graph.node_count,
            edge_count=graph.edge_count,
        )
        options = parameters or {}
        await self._dispatch(organization_id, algorithm, graph, options, outcome)
        outcome.duration_ms = (time.monotonic() - started) * 1000
        return outcome

    async def _dispatch(
        self,
        organization_id: UUID,
        algorithm: AnalyticsAlgorithm,
        graph: Graph,
        options: dict[str, Any],
        outcome: AnalyticsOutcome,
    ) -> None:
        """Compute one algorithm into *outcome*.

        Two tables rather than one branch chain. The split is real: the
        first group is pure graph maths, while ``CRITICAL_ASSETS`` and
        ``DEPENDENCY_SCORING`` both need a database read, so folding
        them into one signature would make every pure algorithm pretend
        to be async.
        """
        pure = _PURE_ALGORITHMS.get(algorithm)
        if pure is not None:
            outcome.values, outcome.ranked = pure(self, graph, options)
            return

        needs_database = _DATABASE_ALGORITHMS.get(algorithm)
        if needs_database is not None:
            outcome.values, outcome.ranked = await needs_database(
                self, organization_id, graph, options
            )
            return

        supported = ", ".join(
            sorted(str(one) for one in (*_PURE_ALGORITHMS, *_DATABASE_ALGORITHMS))
        )
        raise ValidationError(
            f"Unknown analytics algorithm {str(algorithm)!r}. Supported: {supported}."
        )

    # ---- pure algorithms -------------------------------------------

    def _degree(self, graph: Graph, _options: dict[str, Any]) -> _Computed:
        """Degree centrality, plus the directed breakdowns."""
        scores = degree_centrality(graph)
        return (
            {
                "degree": scores,
                "in_degree": in_degree(graph),
                "out_degree": out_degree(graph),
            },
            _rank(scores),
        )

    def _betweenness(self, graph: Graph, _options: dict[str, Any]) -> _Computed:
        """Betweenness centrality -- the chokepoint finder."""
        scores = betweenness_centrality(graph)
        return {"betweenness": scores}, _rank(scores)

    def _pagerank(self, graph: Graph, options: dict[str, Any]) -> _Computed:
        """PageRank over incoming edges."""
        scores = pagerank(
            graph,
            iterations=int(options.get("iterations", self._iterations)),
            damping=float(options.get("damping", self._damping)),
        )
        return {"pagerank": scores}, _rank(scores)

    def _communities(self, graph: Graph, _options: dict[str, Any]) -> _Computed:
        """Label-propagation communities."""
        communities = community_detection(graph)
        return {"communities": communities}, _community_sizes(communities)

    def _components(self, graph: Graph, _options: dict[str, Any]) -> _Computed:
        """Connected components, largest first."""
        components = connected_components(graph)
        return (
            {
                "component_count": len(components),
                "largest": components[0] if components else [],
            },
            [
                {"key": f"component-{index}", "score": len(members)}
                for index, members in enumerate(components)
            ],
        )

    def _path_length(self, graph: Graph, options: dict[str, Any]) -> _Computed:
        """Hop count between two nodes."""
        return self._shortest_path(graph, options), []

    def _risk(self, graph: Graph, options: dict[str, Any]) -> _Computed:
        """Risk propagation from a set of failed nodes.

        Raises:
            ValidationError: If no failed nodes were named. Propagating
                from nothing returns an empty map that reads as "no
                risk" rather than "you did not say what failed".
        """
        failed = [str(one) for one in options.get("failed_keys") or []]
        if not failed:
            raise ValidationError(
                "Risk propagation needs a 'failed_keys' list naming the nodes that have failed."
            )
        risk = risk_propagation(graph, failed_keys=failed)
        return {"risk": risk, "failed_keys": failed}, _rank(risk)

    def _density(self, graph: Graph, _options: dict[str, Any]) -> _Computed:
        """How connected the graph is."""
        return (
            {
                "density": relationship_density(graph),
                "node_count": graph.node_count,
                "edge_count": graph.edge_count,
            },
            [],
        )

    # ---- algorithms needing a database read -------------------------

    async def _critical(
        self, organization_id: UUID, graph: Graph, _options: dict[str, Any]
    ) -> _Computed:
        """Critical assets, blending topology with declared criticality."""
        declared = await self._declared_criticality(organization_id)
        ranked = critical_assets(graph, criticality=declared)
        return {"critical_assets": ranked}, ranked

    async def _dependency_scoring(
        self, organization_id: UUID, _graph: Graph, options: dict[str, Any]
    ) -> _Computed:
        """How dependency-heavy one node is.

        Raises:
            ValidationError: If no root node was named.
        """
        root = options.get("root_key")
        if not root:
            raise ValidationError("Dependency scoring needs a 'root_key'.")
        analysis = await self._dependencies.dependencies(organization_id, str(root))
        return (
            {
                "root_key": root,
                "dependency_score": dependency_score(analysis),
                "affected_count": analysis.affected_count,
            },
            [],
        )

    @staticmethod
    def _shortest_path(graph: Graph, options: dict[str, Any]) -> dict[str, Any]:
        """Hop count between two nodes, or ``None`` if unconnected.

        Raises:
            ValidationError: If either endpoint is missing.
        """
        source, target = options.get("from_key"), options.get("to_key")
        if not source or not target:
            raise ValidationError("Shortest path needs both 'from_key' and 'to_key'.")
        hops = shortest_path_length(graph, source=str(source), target=str(target))
        return {
            "from_key": source,
            "to_key": target,
            "hops": hops,
            "connected": hops is not None,
        }

    async def _declared_criticality(self, organization_id: UUID) -> dict[str, float]:
        """Operator-declared criticality per node.

        Nothing computed from topology can know that a structurally
        peripheral node is the one thing the business cannot lose, which
        is why critical-asset scoring blends this with PageRank and
        betweenness rather than relying on either.
        """
        rows = await self._metadata.list_for_org(organization_id, limit=10_000)
        return {row.node_key: row.criticality for row in rows if row.criticality}

    async def _require_analysable(self, organization_id: UUID) -> None:
        """Refuse an organization whose graph is too large to load whole.

        Raises:
            ValidationError: If it exceeds the ceiling, naming the real
                total rather than the truncated one.
        """
        total = await self._graph.count_nodes(organization_id)
        if total > self._max_nodes:
            raise ValidationError(
                f"This graph has {total:,} nodes, above the "
                f"{self._max_nodes:,}-node analytics ceiling. Narrow the scope by "
                "node type or project, or raise "
                "AIIOS_KNOWLEDGE_GRAPH_SERVICE_ANALYTICS_MAX_NODES."
            )

    async def _load(self, organization_id: UUID) -> Graph:
        """Read the organization's graph into an adjacency view."""
        return Graph.from_subgraph(
            await self._graph.collect_graph(organization_id, max_nodes=self._max_nodes)
        )

    async def _store(
        self,
        organization_id: UUID,
        result: AnalysisResult,
        *,
        kind: QueryKind,
        title: str,
        actor_id: UUID | None,
    ) -> GraphReport:
        """Persist one analysis with the parameters that produced it."""
        return await self._reports.create(
            GraphReport(
                organization_id=organization_id,
                title=title,
                kind=kind,
                root_key=result.root.key,
                parameters={
                    "depth": result.depth,
                    "direction": str(result.direction),
                },
                summary=(f"{result.affected_count} nodes affected, severity {result.severity}."),
                result=result.as_dict(),
                affected_count=result.affected_count,
                risk_score=result.risk_score,
                generated_by=actor_id,
                generated_at=datetime.now(UTC),
            )
        )

    async def reports(
        self,
        organization_id: UUID,
        *,
        kind: QueryKind | None = None,
        limit: int = 100,
    ) -> list[GraphReport]:
        """Stored analyses, newest first."""
        return await self._reports.list_for_org(organization_id, kind=kind, limit=limit)


def _rank(scores: dict[str, float]) -> list[dict[str, Any]]:
    """The top entries of a score map, highest first."""
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [{"key": key, "score": round(float(value), 6)} for key, value in ordered[:_TOP_N]]


def _community_sizes(communities: dict[str, int]) -> list[dict[str, Any]]:
    """How large each detected community is, largest first."""
    sizes: dict[int, int] = {}
    for label in communities.values():
        sizes[label] = sizes.get(label, 0) + 1
    return [
        {"key": f"community-{label}", "score": size}
        for label, size in sorted(sizes.items(), key=lambda item: (-item[1], item[0]))
    ]


_PURE_ALGORITHMS: dict[
    AnalyticsAlgorithm, Callable[[AnalyticsService, Graph, dict[str, Any]], _Computed]
] = {
    AnalyticsAlgorithm.DEGREE_CENTRALITY: AnalyticsService._degree,
    AnalyticsAlgorithm.BETWEENNESS_CENTRALITY: AnalyticsService._betweenness,
    AnalyticsAlgorithm.PAGERANK: AnalyticsService._pagerank,
    AnalyticsAlgorithm.COMMUNITY_DETECTION: AnalyticsService._communities,
    AnalyticsAlgorithm.CONNECTED_COMPONENTS: AnalyticsService._components,
    AnalyticsAlgorithm.SHORTEST_PATH: AnalyticsService._path_length,
    AnalyticsAlgorithm.RISK_PROPAGATION: AnalyticsService._risk,
    AnalyticsAlgorithm.RELATIONSHIP_DENSITY: AnalyticsService._density,
}
"""Algorithms that need only the graph in memory."""

_DATABASE_ALGORITHMS: dict[
    AnalyticsAlgorithm,
    Callable[[AnalyticsService, UUID, Graph, dict[str, Any]], Awaitable[_Computed]],
] = {
    AnalyticsAlgorithm.CRITICAL_ASSETS: AnalyticsService._critical,
    AnalyticsAlgorithm.DEPENDENCY_SCORING: AnalyticsService._dependency_scoring,
}
"""Algorithms that also read PostgreSQL.

Every :class:`~app.models.enums.AnalyticsAlgorithm` member appears in
one table or the other, and a test asserts it -- an algorithm the API
offers with no handler would fail at request time rather than at import
time.
"""


__all__ = [
    "AnalyticsOutcome",
    "AnalyticsService",
]
