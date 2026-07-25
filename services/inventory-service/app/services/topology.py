"""Topology traversal, backed by Neo4j and cached in Postgres.

Per docs/036 "TOPOLOGY": Dependency Graph, Relationship Traversal,
Impact Analysis. See ``app/models/asset_topology_cache.py``'s own
docstring for why repeated traversals for the same asset are cached
rather than always round-tripping to Neo4j.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.models.asset_topology_cache import AssetTopologyCacheEntry
from app.models.enums import RelationshipType
from app.repositories.asset_topology_cache import AssetTopologyCacheRepository
from app.topology.graph import TopologyGraphClient

_CACHE_TTL = timedelta(minutes=5)
_GraphCompute = Callable[[], Awaitable[list[dict[str, Any]]]]


class TopologyService:
    """Resolves topology queries, using the Postgres cache when fresh."""

    def __init__(self, graph: TopologyGraphClient, cache: AssetTopologyCacheRepository) -> None:
        self._graph = graph
        self._cache = cache

    async def _cached_or_compute(
        self,
        asset_id: UUID,
        *,
        organization_id: UUID,
        query_kind: str,
        compute: _GraphCompute,
    ) -> list[dict[str, Any]]:
        entry = await self._cache.get_by_query_kind(asset_id, query_kind)
        now = datetime.now(UTC)
        if entry is not None and entry.expires_at > now:
            result: list[dict[str, Any]] = entry.payload["nodes"]
            return result

        nodes = await compute()
        payload = {"nodes": nodes}
        if entry is not None:
            entry.payload = payload
            entry.computed_at = now
            entry.expires_at = now + _CACHE_TTL
        else:
            await self._cache.create(
                AssetTopologyCacheEntry(
                    asset_id=asset_id,
                    organization_id=organization_id,
                    query_kind=query_kind,
                    payload=payload,
                    computed_at=now,
                    expires_at=now + _CACHE_TTL,
                )
            )
        return nodes

    async def get_neighbors(self, asset_id: UUID, *, organization_id: UUID) -> list[dict[str, Any]]:
        """Every asset directly connected to *asset_id* ("Relationship Traversal")."""
        return await self._cached_or_compute(
            asset_id,
            organization_id=organization_id,
            query_kind="neighbors",
            compute=lambda: self._graph.get_neighbors(asset_id),
        )

    async def get_dependency_graph(
        self, asset_id: UUID, *, organization_id: UUID, depth: int = 2
    ) -> list[dict[str, Any]]:
        """Every asset *asset_id* transitively depends on ("Dependency Graph")."""
        return await self._cached_or_compute(
            asset_id,
            organization_id=organization_id,
            query_kind=f"dependency:{depth}",
            compute=lambda: self._graph.get_dependency_graph(asset_id, depth=depth),
        )

    async def get_impact_analysis(
        self, asset_id: UUID, *, organization_id: UUID, depth: int = 2
    ) -> list[dict[str, Any]]:
        """Every asset that would be affected if *asset_id* became
        unavailable ("Impact Analysis").
        """
        return await self._cached_or_compute(
            asset_id,
            organization_id=organization_id,
            query_kind=f"impact:{depth}",
            compute=lambda: self._graph.get_impact_analysis(asset_id, depth=depth),
        )

    async def sync_asset_node(
        self, asset_id: UUID, *, organization_id: UUID, asset_type: str, name: str
    ) -> None:
        """Mirror an asset's identity into the graph ("Integrate with Neo4j")."""
        await self._graph.upsert_asset_node(
            asset_id, organization_id=organization_id, asset_type=asset_type, name=name
        )

    async def remove_asset_node(self, asset_id: UUID) -> None:
        """Remove an asset's node (and every edge touching it) from the graph."""
        await self._graph.delete_asset_node(asset_id)

    async def sync_relationship(
        self, source_asset_id: UUID, target_asset_id: UUID, relationship_type: RelationshipType
    ) -> None:
        """Mirror a relationship edge into the graph."""
        await self._graph.upsert_relationship(source_asset_id, target_asset_id, relationship_type)

    async def remove_relationship(
        self, source_asset_id: UUID, target_asset_id: UUID, relationship_type: RelationshipType
    ) -> None:
        """Remove a relationship edge's mirror from the graph."""
        await self._graph.delete_relationship(source_asset_id, target_asset_id, relationship_type)


__all__ = ["TopologyService"]
