"""Graph statistics ("GET /graph/statistics").

**Every figure is derived from the graph, never incremented.** A counter
bumped on each node write drifts the moment one write is lost, and
nothing can tell you that it has. Recomputing means every number is
explainable by something you can go and count.

Two figures are worth more than they look:

- **Orphan count** -- nodes with no relationships at all. Almost always
  a synchronization bug rather than a fact about the estate, which is
  why it gets its own number instead of hiding inside the node count.
- **Connected components** -- more than one usually means a sync gap,
  not genuinely isolated infrastructure. An estate that has quietly
  split into two graphs still answers every single-node query correctly,
  so this is the figure that surfaces it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.analytics.algorithms import (
    Graph,
    connected_components,
    critical_assets,
    relationship_density,
)
from app.cypher.builder import MAX_LIMIT_CEILING
from app.digital_twin.twin import DigitalTwinService
from app.graph.repository import GraphRepository
from app.models.graph_statistics import GraphStatistics
from app.repositories.graph_metadata import GraphMetadataRepository
from app.repositories.graph_statistics import GraphStatisticsRepository
from app.repositories.graph_sync_job import GraphSyncJobRepository
from app.synchronization.engine import source_of, status_of

_TOP_CRITICAL = 10


class StatisticsService:
    """Computes and stores an organization's graph statistics."""

    def __init__(
        self,
        graph: GraphRepository,
        statistics: GraphStatisticsRepository,
        metadata: GraphMetadataRepository,
        sync_jobs: GraphSyncJobRepository,
        twins: DigitalTwinService,
        *,
        max_nodes: int = MAX_LIMIT_CEILING,
    ) -> None:
        self._graph = graph
        self._statistics = statistics
        self._metadata = metadata
        self._sync_jobs = sync_jobs
        self._twins = twins
        self._max_nodes = max_nodes

    async def compute(self, organization_id: UUID) -> dict[str, Any]:
        """Compute a rollup without storing it.

        Every read is sequential. An ``AsyncSession`` is not safe for
        concurrent use even for reads, so gathering these would be a
        latent ``InterfaceError`` under load rather than a speed-up.
        """
        node_count = await self._graph.count_nodes(organization_id)
        relationship_count = await self._graph.count_relationships(organization_id)
        node_types = await self._graph.type_counts(organization_id)
        edge_types = await self._graph.relationship_type_counts(organization_id)
        orphans = await self._graph.orphan_keys(organization_id, limit=1_000)
        degrees = await self._graph.degrees(organization_id, limit=self._max_nodes)

        structure = await self._structure(organization_id, node_count)
        return {
            "node_count": node_count,
            "relationship_count": relationship_count,
            "node_type_counts": node_types,
            "relationship_type_counts": edge_types,
            "orphan_count": len(orphans),
            "average_degree": (round(sum(degrees.values()) / len(degrees), 4) if degrees else 0.0),
            "max_degree": max(degrees.values(), default=0),
            "density": structure["density"],
            "connected_components": structure["connected_components"],
            "critical_assets": structure["critical_assets"],
            "twin_counts": await self._twins.twin_counts(organization_id),
            "sync_health": await self._sync_health(organization_id),
        }

    async def refresh(self, organization_id: UUID) -> GraphStatistics:
        """Recompute and persist the organization's rollup.

        Updated in place rather than appended: the graph itself is the
        history, and a second copy of these numbers would only be
        another thing to keep consistent.
        """
        values = await self.compute(organization_id)
        existing = await self._statistics.get_for_org(organization_id)
        if existing is not None:
            for column, value in values.items():
                setattr(existing, column, value)
            existing.computed_at = datetime.now(UTC)
            return await self._statistics.update(existing)
        return await self._statistics.create(
            GraphStatistics(
                organization_id=organization_id,
                computed_at=datetime.now(UTC),
                **values,
            )
        )

    async def get(self, organization_id: UUID) -> GraphStatistics | None:
        """The stored rollup, or ``None`` if none has been computed."""
        return await self._statistics.get_for_org(organization_id)

    async def _structure(self, organization_id: UUID, node_count: int) -> dict[str, Any]:
        """Density, components, and critical assets.

        Skipped above the analytics ceiling rather than attempted: these
        need the whole graph in memory, and refusing one section of a
        statistics response beats making the whole endpoint time out on
        a large estate.
        """
        if node_count > self._max_nodes:
            return {
                "density": 0.0,
                "connected_components": 0,
                "critical_assets": [],
                "skipped": (
                    f"structural analysis skipped: {node_count:,} nodes exceeds the "
                    f"{self._max_nodes:,}-node ceiling"
                ),
            }

        graph = Graph.from_subgraph(
            await self._graph.collect_graph(organization_id, max_nodes=self._max_nodes)
        )
        declared = {
            row.node_key: row.criticality
            for row in await self._metadata.list_for_org(organization_id, limit=10_000)
            if row.criticality
        }
        return {
            "density": relationship_density(graph),
            "connected_components": len(connected_components(graph)),
            "critical_assets": critical_assets(graph, criticality=declared, limit=_TOP_CRITICAL),
        }

    async def _sync_health(self, organization_id: UUID) -> dict[str, Any]:
        """The state of each source's most recent synchronization.

        Normalised through :func:`app.synchronization.engine.status_of`
        and ``source_of``: these rows come back from Postgres as strings,
        and a summary keyed by a mix of enum members and strings would
        double-count.
        """
        recent = await self._sync_jobs.list_for_org(organization_id, limit=200)
        latest: dict[str, dict[str, Any]] = {}
        for job in recent:
            name = str(source_of(job))
            if name in latest:
                continue
            latest[name] = {
                "status": str(status_of(job)),
                "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "nodes": job.nodes_created,
                "relationships": job.relationships_created,
                "consecutive_failures": job.consecutive_failures,
                "error": job.error,
            }
        failing = [name for name, one in latest.items() if one["consecutive_failures"]]
        return {
            "sources": latest,
            "failing_sources": sorted(failing),
            "healthy": not failing,
        }


__all__ = ["StatisticsService"]
