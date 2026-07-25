"""Neo4j graph operations for asset topology.

Per docs/036 "TOPOLOGY": Dependency Graph, Network Graph, Application
Graph, Infrastructure Graph, Industrial Topology, Cloud Topology,
Kubernetes Topology, Relationship Traversal, Impact Analysis. Rather
than one bespoke Cypher query per named graph type, this client exposes
general-purpose node/edge maintenance plus neighbor/dependency/impact
traversal -- every named "graph" in docs/036 is really the same
underlying asset graph, filtered to a subset of
:class:`~app.models.enums.AssetType` values at the *service* layer
(``app/services/topology.py``), not a distinct Cypher query each.

Postgres (``asset_relationships``) stays the authoritative,
transactional store; every write here is a best-effort mirror the
service layer keeps in sync on create/delete, so this client's own
failure never blocks the relational write it's mirroring.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from neo4j import AsyncDriver

from app.models.enums import RelationshipType

_TRAVERSAL_RELATIONSHIP_TYPES = "DEPENDS_ON|RUNS_ON|HOSTED_BY"
_MAX_TRAVERSAL_DEPTH = 5


def _relationship_label(relationship_type: RelationshipType) -> str:
    """Convert a :class:`RelationshipType` value into a Neo4j-safe
    relationship type identifier (e.g. ``depends_on`` -> ``DEPENDS_ON``).
    Safe to interpolate directly into Cypher text: the input is always
    one of a fixed, known set of enum values, never free-form user text.

    ``str()``, not ``.value`` -- *relationship_type* may be a genuine
    :class:`RelationshipType` member or the raw string SQLAlchemy's
    weakly-referenced identity map handed back for a row reloaded in a
    later request (the enum-typed-as-``String``-column, GC'd-identity-
    map interaction documented in ``services/secrets-management-service``
    ``SecretService.update()``'s own docstring, caught live here too via
    ``AssetRelationshipService.delete()``). ``RelationshipType`` is a
    ``StrEnum``, so ``str()`` gives the identical result either way.
    """
    return str(relationship_type).upper()


class TopologyGraphClient:
    """Thin wrapper over the Neo4j driver for asset topology operations."""

    def __init__(self, driver: AsyncDriver, *, database: str = "neo4j") -> None:
        self._driver = driver
        self._database = database

    async def upsert_asset_node(
        self, asset_id: UUID, *, organization_id: UUID, asset_type: str, name: str
    ) -> None:
        """Create or update the graph node representing *asset_id*."""
        query = (
            "MERGE (a:Asset {id: $asset_id}) "
            "SET a.organization_id = $organization_id, "
            "a.asset_type = $asset_type, a.name = $name"
        )
        async with self._driver.session(database=self._database) as session:
            await session.run(
                query,
                asset_id=str(asset_id),
                organization_id=str(organization_id),
                asset_type=asset_type,
                name=name,
            )

    async def delete_asset_node(self, asset_id: UUID) -> None:
        """Remove *asset_id*'s node and every relationship touching it."""
        query = "MATCH (a:Asset {id: $asset_id}) DETACH DELETE a"
        async with self._driver.session(database=self._database) as session:
            await session.run(query, asset_id=str(asset_id))

    async def upsert_relationship(
        self,
        source_asset_id: UUID,
        target_asset_id: UUID,
        relationship_type: RelationshipType,
    ) -> None:
        """Create or confirm a directed edge between two asset nodes."""
        label = _relationship_label(relationship_type)
        query = (
            "MATCH (source:Asset {id: $source_id}), (target:Asset {id: $target_id}) "
            f"MERGE (source)-[:{label}]->(target)"
        )
        async with self._driver.session(database=self._database) as session:
            await session.run(query, source_id=str(source_asset_id), target_id=str(target_asset_id))

    async def delete_relationship(
        self,
        source_asset_id: UUID,
        target_asset_id: UUID,
        relationship_type: RelationshipType,
    ) -> None:
        """Remove one directed edge between two asset nodes."""
        label = _relationship_label(relationship_type)
        query = (
            "MATCH (source:Asset {id: $source_id})"
            f"-[r:{label}]->"
            "(target:Asset {id: $target_id}) "
            "DELETE r"
        )
        async with self._driver.session(database=self._database) as session:
            await session.run(query, source_id=str(source_asset_id), target_id=str(target_asset_id))

    async def get_neighbors(self, asset_id: UUID) -> list[dict[str, Any]]:
        """Every asset directly connected to *asset_id*, in either
        direction ("Relationship Traversal").
        """
        query = (
            "MATCH (a:Asset {id: $asset_id})-[r]-(neighbor:Asset) "
            "RETURN neighbor.id AS id, neighbor.name AS name, "
            "neighbor.asset_type AS asset_type, type(r) AS relationship_type, "
            "startNode(r).id = a.id AS outgoing"
        )
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query, asset_id=str(asset_id))
            return [dict(record) async for record in result]

    async def get_dependency_graph(self, asset_id: UUID, *, depth: int = 2) -> list[dict[str, Any]]:
        """Every asset *asset_id* transitively depends on, up to *depth*
        hops out ("Dependency Graph").
        """
        bounded_depth = max(1, min(depth, _MAX_TRAVERSAL_DEPTH))
        query = (
            "MATCH path = (a:Asset {id: $asset_id})"
            f"-[:{_TRAVERSAL_RELATIONSHIP_TYPES}*1..{bounded_depth}]->"
            "(dependency:Asset) "
            "RETURN DISTINCT dependency.id AS id, dependency.name AS name, "
            "dependency.asset_type AS asset_type, length(path) AS distance "
            "ORDER BY distance"
        )
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query, asset_id=str(asset_id))
            return [dict(record) async for record in result]

    async def get_impact_analysis(self, asset_id: UUID, *, depth: int = 2) -> list[dict[str, Any]]:
        """Every asset that would be affected if *asset_id* became
        unavailable -- everything transitively depending *on* it, up to
        *depth* hops ("Impact Analysis").
        """
        bounded_depth = max(1, min(depth, _MAX_TRAVERSAL_DEPTH))
        query = (
            "MATCH path = (dependent:Asset)"
            f"-[:{_TRAVERSAL_RELATIONSHIP_TYPES}*1..{bounded_depth}]->"
            "(a:Asset {id: $asset_id}) "
            "RETURN DISTINCT dependent.id AS id, dependent.name AS name, "
            "dependent.asset_type AS asset_type, length(path) AS distance "
            "ORDER BY distance"
        )
        async with self._driver.session(database=self._database) as session:
            result = await session.run(query, asset_id=str(asset_id))
            return [dict(record) async for record in result]


__all__ = ["TopologyGraphClient"]
