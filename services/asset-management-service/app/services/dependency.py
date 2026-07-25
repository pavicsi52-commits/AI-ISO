"""Dependency analysis. Per docs/038 "DEPENDENCY ANALYSIS": Integrate
with Neo4j; Impact Analysis, Dependency Graph, Service/Application/
Infrastructure Dependency, Blast Radius Analysis, Root Cause
Relationships. Queries the read-only :class:`~app.dependencies
.graph_client.DependencyGraphClient` against the graph
``inventory-service`` already populates, then caches the result.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.dependencies.graph_client import DependencyGraphClient
from app.models.asset_dependency_analysis import AssetDependencyAnalysis
from app.repositories.asset_dependency_analysis import AssetDependencyAnalysisRepository
from app.repositories.managed_asset import ManagedAssetRepository


class DependencyService:
    """Analyzes and caches a managed asset's dependency graph."""

    def __init__(
        self,
        analyses: AssetDependencyAnalysisRepository,
        managed_assets: ManagedAssetRepository,
        graph: DependencyGraphClient,
    ) -> None:
        self._analyses = analyses
        self._managed_assets = managed_assets
        self._graph = graph

    async def get_cached(self, managed_asset_id: UUID) -> AssetDependencyAnalysis | None:
        """Return *managed_asset_id*'s last-computed dependency analysis, or ``None``."""
        return await self._analyses.get_for_managed_asset(managed_asset_id)

    async def analyze(
        self, managed_asset_id: UUID, *, depth: int = 2
    ) -> tuple[AssetDependencyAnalysis, dict[str, list[dict[str, object]]]]:
        """Run a live dependency analysis against Neo4j for *managed_asset_id*
        ("Impact Analysis", "Dependency Graph", "Blast Radius Analysis",
        "Root Cause Relationships"), caching the summary counts.
        """
        managed_asset = await self._managed_assets.require_by_id(managed_asset_id)
        inventory_asset_id = managed_asset.inventory_asset_id

        dependency_graph = await self._graph.get_dependency_graph(inventory_asset_id, depth=depth)
        impact_analysis = await self._graph.get_impact_analysis(inventory_asset_id, depth=depth)
        blast_radius = await self._graph.get_blast_radius(inventory_asset_id)
        root_cause_candidates = await self._graph.get_root_cause_candidates(inventory_asset_id)

        now = datetime.now(UTC)
        graph_snapshot = {
            "dependency_graph": dependency_graph,
            "impact_analysis": impact_analysis,
            "blast_radius": blast_radius,
            "root_cause_candidates": root_cause_candidates,
        }

        existing = await self.get_cached(managed_asset_id)
        if existing is not None:
            existing.dependency_count = len(dependency_graph)
            existing.dependent_count = len(impact_analysis)
            existing.blast_radius_count = len(blast_radius)
            existing.graph_snapshot = graph_snapshot
            existing.computed_at = now
            analysis = existing
        else:
            analysis = await self._analyses.create(
                AssetDependencyAnalysis(
                    managed_asset_id=managed_asset_id,
                    organization_id=managed_asset.organization_id,
                    dependency_count=len(dependency_graph),
                    dependent_count=len(impact_analysis),
                    blast_radius_count=len(blast_radius),
                    graph_snapshot=graph_snapshot,
                    computed_at=now,
                )
            )
        return analysis, graph_snapshot


__all__ = ["DependencyService"]
