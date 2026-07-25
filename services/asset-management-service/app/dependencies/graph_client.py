"""Read-only Neo4j graph queries for dependency analysis.

Per docs/038's own framing ("Inventory identifies assets. Asset
Management manages assets.") and its "DEPENDENCY ANALYSIS" section
("Integrate with Neo4j."), this service never writes graph nodes or
edges -- ``services/inventory-service``'s own ``app/topology/graph.py``
already owns that, mirroring its authoritative Postgres
``asset_relationships`` table into ``:Asset`` nodes keyed by that
service's own asset ID. Every :class:`~app.models.managed_asset
.ManagedAsset` carries the matching ``inventory_asset_id``, so this
client queries that *same* graph read-only, keyed by that id -- it
never creates a second, competing asset-relationship model.

"Service Dependency"/"Application Dependency"/"Infrastructure
Dependency" are the same underlying graph filtered by
``inventory-service``'s own ``AssetType`` at the *service* layer
(``app/services/dependency.py``), not three distinct Cypher queries --
the same "one general client, named-graph-as-filtered-view" design
``TopologyGraphClient`` established.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from neo4j import AsyncDriver

_TRAVERSAL_RELATIONSHIP_TYPES = "DEPENDS_ON|RUNS_ON|HOSTED_BY"
_MAX_TRAVERSAL_DEPTH = 5


def _bounded_depth(depth: int) -> int:
    return max(1, min(depth, _MAX_TRAVERSAL_DEPTH))


class DependencyGraphClient:
    """Thin, read-only wrapper over the Neo4j driver for dependency analysis."""

    def __init__(self, driver: AsyncDriver, *, database: str = "neo4j") -> None:
        self._driver = driver
        self._database = database

    async def get_neighbors(self, inventory_asset_id: UUID) -> list[dict[str, Any]]:
        """Every asset directly connected to *inventory_asset_id*, in either direction."""
        query = (
            "MATCH (a:Asset {id: $asset_id})-[r]-(neighbor:Asset) "
            "RETURN neighbor.id AS id, neighbor.name AS name, "
            "neighbor.asset_type AS asset_type, type(r) AS relationship_type, "
            "startNode(r).id = a.id AS outgoing"
        )
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query, asset_id=str(inventory_asset_id))
            return [dict(record) async for record in result]

    async def get_dependency_graph(
        self, inventory_asset_id: UUID, *, depth: int = 2
    ) -> list[dict[str, Any]]:
        """Every asset *inventory_asset_id* transitively depends on, up to
        *depth* hops out ("Dependency Graph").
        """
        bounded_depth = _bounded_depth(depth)
        query = (
            "MATCH path = (a:Asset {id: $asset_id})"
            f"-[:{_TRAVERSAL_RELATIONSHIP_TYPES}*1..{bounded_depth}]->"
            "(dependency:Asset) "
            "RETURN DISTINCT dependency.id AS id, dependency.name AS name, "
            "dependency.asset_type AS asset_type, length(path) AS distance "
            "ORDER BY distance"
        )
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query, asset_id=str(inventory_asset_id))
            return [dict(record) async for record in result]

    async def get_impact_analysis(
        self, inventory_asset_id: UUID, *, depth: int = 2
    ) -> list[dict[str, Any]]:
        """Every asset that would be affected if *inventory_asset_id* became
        unavailable -- everything transitively depending *on* it, up to
        *depth* hops ("Impact Analysis").
        """
        bounded_depth = _bounded_depth(depth)
        query = (
            "MATCH path = (dependent:Asset)"
            f"-[:{_TRAVERSAL_RELATIONSHIP_TYPES}*1..{bounded_depth}]->"
            "(a:Asset {id: $asset_id}) "
            "RETURN DISTINCT dependent.id AS id, dependent.name AS name, "
            "dependent.asset_type AS asset_type, length(path) AS distance "
            "ORDER BY distance"
        )
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query, asset_id=str(inventory_asset_id))
            return [dict(record) async for record in result]

    async def get_blast_radius(
        self, inventory_asset_id: UUID, *, depth: int = _MAX_TRAVERSAL_DEPTH
    ) -> list[dict[str, Any]]:
        """Every asset within *inventory_asset_id*'s full failure blast
        radius ("Blast Radius Analysis") -- the same transitive-dependent
        traversal as :meth:`get_impact_analysis`, defaulted to the maximum
        supported depth rather than a shallow "immediate impact" view.
        """
        return await self.get_impact_analysis(inventory_asset_id, depth=depth)

    async def get_root_cause_candidates(
        self, inventory_asset_id: UUID, *, depth: int = _MAX_TRAVERSAL_DEPTH
    ) -> list[dict[str, Any]]:
        """*inventory_asset_id*'s upstream dependency chain, furthest hop
        first ("Root Cause Relationships") -- when an asset is symptomatic,
        the assets it depends on furthest upstream are the most likely
        root-cause candidates, so this reorders
        :meth:`get_dependency_graph`'s same traversal by descending
        distance instead of ascending.
        """
        bounded_depth = _bounded_depth(depth)
        query = (
            "MATCH path = (a:Asset {id: $asset_id})"
            f"-[:{_TRAVERSAL_RELATIONSHIP_TYPES}*1..{bounded_depth}]->"
            "(dependency:Asset) "
            "RETURN DISTINCT dependency.id AS id, dependency.name AS name, "
            "dependency.asset_type AS asset_type, length(path) AS distance "
            "ORDER BY distance DESC"
        )
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query, asset_id=str(inventory_asset_id))
            return [dict(record) async for record in result]


__all__ = ["DependencyGraphClient"]
