"""Node and relationship CRUD over Neo4j ("Relationship Engine").

Every statement here is built by :mod:`app.cypher.builder`, so the only
things ever formatted into query text are validated labels, validated
relationship types, and bounded depths. Everything else is a bound
parameter -- including, always, ``organization_id``.

**Writes are ``MERGE``, not ``CREATE``.** Synchronization re-runs
constantly, and a ``CREATE`` would double the graph every time. ``MERGE``
on ``(key, organization_id)`` -- the uniqueness constraint
:mod:`app.graph.schema` declares -- makes every write idempotent, which
is what lets a full sync be safe to run whenever anyone is unsure.

**Deletes are ``DETACH DELETE``.** A node removed without its
relationships leaves dangling edges that every traversal then has to
step around.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from shared_core.exceptions.not_found import NotFoundError
from shared_core.logging.logger import get_logger

from app.cypher.builder import (
    MAX_LIMIT_CEILING,
    label_clause,
    order_clause,
    traversal_pattern,
    validate_depth,
    validate_label,
    validate_limit,
    validate_relationship_type,
    validate_relationship_types,
)
from app.graph.client import GraphClient
from app.graph.entities import (
    GraphNode,
    GraphRelationship,
    NodeInput,
    RelationshipInput,
    Subgraph,
    validate_node_input,
    validate_relationship_input,
)
from app.graph.schema import GRAPH_NODE_LABEL
from app.models.enums import NodeType, RelationshipType, TraversalDirection

logger = get_logger("app.graph.repository")

_NODE_RETURN = "properties(n) AS node"
_MAX_LIMIT = MAX_LIMIT_CEILING


class GraphRepository:
    """Reads and writes nodes and relationships."""

    def __init__(
        self,
        client: GraphClient,
        *,
        max_depth: int = 6,
        max_nodes: int = 5_000,
    ) -> None:
        self._client = client
        self._max_depth = max_depth
        self._max_nodes = max_nodes

    @property
    def client(self) -> GraphClient:
        """The underlying Neo4j client."""
        return self._client

    # ---- nodes -----------------------------------------------------

    async def upsert_node(
        self, organization_id: UUID, node: NodeInput, *, source: str | None = None
    ) -> GraphNode:
        """Create or update one node, idempotently.

        Raises:
            ValidationError: If the node type is not a known label.
            DependencyError: If the graph is unreachable.
        """
        validate_node_input(node)
        label = validate_label(node.node_type)
        cypher = (
            f"MERGE (n:{GRAPH_NODE_LABEL}:{label} "
            "{key: $key, organization_id: $organization_id}) "
            "ON CREATE SET n.created_at = datetime() "
            "SET n.node_type = $node_type, "
            "    n.name = $name, "
            "    n.description = $description, "
            "    n.project_id = $project_id, "
            "    n.source = $source, "
            "    n.updated_at = datetime(), "
            "    n += $properties "
            f"RETURN {_NODE_RETURN}"
        )
        result = await self._client.write(
            cypher,
            {
                "key": node.key,
                "organization_id": str(organization_id),
                "node_type": str(node.node_type),
                "name": node.name,
                "description": node.description,
                "project_id": node.project_id,
                "source": source or node.source,
                "properties": node.properties,
            },
        )
        return GraphNode.from_record(result.scalar("node", {}))

    async def upsert_nodes(
        self, organization_id: UUID, nodes: Sequence[NodeInput], *, source: str | None = None
    ) -> int:
        """Create or update many nodes in one transaction; returns how many.

        Grouped by label because a Cypher label cannot be parameterised
        -- one ``UNWIND`` statement per label rather than one statement
        per node, which is the difference between a bulk import taking
        minutes and taking hours.
        """
        if not nodes:
            return 0
        by_label: dict[str, list[dict[str, Any]]] = {}
        for node in nodes:
            validate_node_input(node)
            label = validate_label(node.node_type)
            by_label.setdefault(label, []).append(
                {
                    "key": node.key,
                    "node_type": str(node.node_type),
                    "name": node.name,
                    "description": node.description,
                    "project_id": node.project_id,
                    "source": source or node.source,
                    "properties": node.properties,
                }
            )

        statements: list[tuple[str, dict[str, Any]]] = []
        for label, rows in by_label.items():
            statements.append(
                (
                    "UNWIND $rows AS row "
                    f"MERGE (n:{GRAPH_NODE_LABEL}:{label} "
                    "{key: row.key, organization_id: $organization_id}) "
                    "ON CREATE SET n.created_at = datetime() "
                    "SET n.node_type = row.node_type, "
                    "    n.name = row.name, "
                    "    n.description = row.description, "
                    "    n.project_id = row.project_id, "
                    "    n.source = row.source, "
                    "    n.updated_at = datetime(), "
                    "    n += row.properties",
                    {"rows": rows, "organization_id": str(organization_id)},
                )
            )
        await self._client.write_many(statements)
        return len(nodes)

    async def get_node(self, organization_id: UUID, key: str) -> GraphNode | None:
        """One node by its business key, or ``None``."""
        result = await self._client.read(
            f"MATCH (n:{GRAPH_NODE_LABEL} "
            "{key: $key, organization_id: $organization_id}) "
            f"RETURN {_NODE_RETURN}",
            {"key": key, "organization_id": str(organization_id)},
        )
        record = result.scalar("node")
        return GraphNode.from_record(record) if record else None

    async def require_node(self, organization_id: UUID, key: str) -> GraphNode:
        """One node by key.

        Raises:
            NotFoundError: If no such node exists in this organization.
        """
        node = await self.get_node(organization_id, key)
        if node is None:
            raise NotFoundError(f"No graph node with key {key!r}.")
        return node

    async def list_nodes(
        self,
        organization_id: UUID,
        *,
        node_types: Sequence[NodeType | str] | None = None,
        project_id: str | None = None,
        source: str | None = None,
        order_by: str | None = "name",
        limit: int = 200,
        offset: int = 0,
    ) -> list[GraphNode]:
        """Nodes for one organization, filtered and paginated.

        Raises:
            ValidationError: If a node type, ordering property, or the
                limit is invalid.
        """
        safe_limit = validate_limit(limit, ceiling=_MAX_LIMIT)
        labels = label_clause(node_types)
        filters = ["n.organization_id = $organization_id"]
        parameters: dict[str, Any] = {
            "organization_id": str(organization_id),
            "limit": safe_limit,
            "offset": max(0, offset),
        }
        if project_id is not None:
            filters.append("n.project_id = $project_id")
            parameters["project_id"] = project_id
        if source is not None:
            filters.append("n.source = $source")
            parameters["source"] = source

        cypher = (
            f"MATCH (n:{GRAPH_NODE_LABEL}{labels}) "
            f"WHERE {' AND '.join(filters)} "
            f"RETURN {_NODE_RETURN}"
            f"{order_clause('n', order_by)} "
            "SKIP $offset LIMIT $limit"
        )
        result = await self._client.read(cypher, parameters)
        return [GraphNode.from_record(row.get("node", {})) for row in result.records]

    async def count_nodes(self, organization_id: UUID) -> int:
        """How many nodes an organization has, counted in the graph."""
        result = await self._client.read(
            f"MATCH (n:{GRAPH_NODE_LABEL} {{organization_id: $organization_id}}) "
            "RETURN count(n) AS total",
            {"organization_id": str(organization_id)},
        )
        return int(result.scalar("total", 0) or 0)

    async def delete_node(self, organization_id: UUID, key: str) -> bool:
        """Delete one node and its relationships; returns whether it existed.

        ``DETACH DELETE`` rather than ``DELETE``: a node removed without
        its edges leaves dangling relationships that every traversal
        then has to step around.
        """
        result = await self._client.write(
            f"MATCH (n:{GRAPH_NODE_LABEL} "
            "{key: $key, organization_id: $organization_id}) "
            "WITH n, count(n) AS found DETACH DELETE n RETURN found",
            {"key": key, "organization_id": str(organization_id)},
        )
        return bool(result.records)

    # ---- relationships ---------------------------------------------

    async def upsert_relationship(
        self, organization_id: UUID, relationship: RelationshipInput
    ) -> GraphRelationship:
        """Create or update one relationship, idempotently.

        Both endpoints must already exist in this organization -- an
        edge is created between nodes, never conjuring them. A sync that
        could invent endpoints would paper over its own ordering bugs
        with half-populated nodes.

        Raises:
            NotFoundError: If either endpoint is missing.
            ValidationError: If the type is unknown or it is a self-loop.
            DependencyError: If the graph is unreachable.
        """
        validate_relationship_input(relationship)
        edge_type = validate_relationship_type(relationship.relationship_type)
        cypher = (
            f"MATCH (a:{GRAPH_NODE_LABEL} "
            "{key: $from_key, organization_id: $organization_id}) "
            f"MATCH (b:{GRAPH_NODE_LABEL} "
            "{key: $to_key, organization_id: $organization_id}) "
            f"MERGE (a)-[r:{edge_type}]->(b) "
            "ON CREATE SET r.created_at = datetime() "
            "SET r.weight = $weight, r.updated_at = datetime(), r += $properties "
            "RETURN properties(r) AS edge"
        )
        result = await self._client.write(
            cypher,
            {
                "from_key": relationship.from_key,
                "to_key": relationship.to_key,
                "organization_id": str(organization_id),
                "weight": relationship.weight,
                "properties": relationship.properties,
            },
        )
        if not result.records:
            raise NotFoundError(
                f"Cannot relate {relationship.from_key!r} to {relationship.to_key!r}: "
                "one or both nodes do not exist in this organization."
            )
        return GraphRelationship.from_record(
            result.scalar("edge", {}),
            from_key=relationship.from_key,
            to_key=relationship.to_key,
            relationship_type=edge_type,
        )

    async def upsert_relationships(
        self, organization_id: UUID, relationships: Sequence[RelationshipInput]
    ) -> int:
        """Create or update many relationships in one transaction.

        Returns how many were *submitted*. An edge whose endpoints are
        missing is silently skipped by the ``MATCH``, which is why the
        import path counts what actually landed rather than trusting
        this number.
        """
        if not relationships:
            return 0
        by_type: dict[str, list[dict[str, Any]]] = {}
        for edge in relationships:
            validate_relationship_input(edge)
            edge_type = validate_relationship_type(edge.relationship_type)
            by_type.setdefault(edge_type, []).append(
                {
                    "from_key": edge.from_key,
                    "to_key": edge.to_key,
                    "weight": edge.weight,
                    "properties": edge.properties,
                }
            )

        statements: list[tuple[str, dict[str, Any]]] = []
        for edge_type, rows in by_type.items():
            statements.append(
                (
                    "UNWIND $rows AS row "
                    f"MATCH (a:{GRAPH_NODE_LABEL} "
                    "{key: row.from_key, organization_id: $organization_id}) "
                    f"MATCH (b:{GRAPH_NODE_LABEL} "
                    "{key: row.to_key, organization_id: $organization_id}) "
                    f"MERGE (a)-[r:{edge_type}]->(b) "
                    "ON CREATE SET r.created_at = datetime() "
                    "SET r.weight = row.weight, r.updated_at = datetime(), "
                    "    r += row.properties",
                    {"rows": rows, "organization_id": str(organization_id)},
                )
            )
        await self._client.write_many(statements)
        return len(relationships)

    async def list_relationships(
        self,
        organization_id: UUID,
        *,
        node_key: str | None = None,
        relationship_types: Sequence[RelationshipType | str] | None = None,
        direction: TraversalDirection = TraversalDirection.BOTH,
        limit: int = 200,
    ) -> list[GraphRelationship]:
        """Relationships for one organization, optionally around one node."""
        safe_limit = validate_limit(limit, ceiling=_MAX_LIMIT)
        pattern = traversal_pattern(
            direction=direction, types=relationship_types, ceiling=self._max_depth
        )
        parameters: dict[str, Any] = {
            "organization_id": str(organization_id),
            "limit": safe_limit,
        }
        if node_key is not None:
            match = (
                f"MATCH (a:{GRAPH_NODE_LABEL} "
                "{key: $node_key, organization_id: $organization_id})"
                f"{pattern}(b:{GRAPH_NODE_LABEL} "
                "{organization_id: $organization_id})"
            )
            parameters["node_key"] = node_key
        else:
            match = (
                f"MATCH (a:{GRAPH_NODE_LABEL} {{organization_id: $organization_id}})"
                f"{pattern}(b:{GRAPH_NODE_LABEL} "
                "{organization_id: $organization_id})"
            )

        cypher = (
            f"{match} "
            "RETURN startNode(r).key AS from_key, endNode(r).key AS to_key, "
            "       type(r) AS edge_type, properties(r) AS edge "
            "LIMIT $limit"
        )
        result = await self._client.read(cypher, parameters)
        return [_edge_from_row(row) for row in result.records]

    async def count_relationships(self, organization_id: UUID) -> int:
        """How many relationships an organization has."""
        result = await self._client.read(
            f"MATCH (a:{GRAPH_NODE_LABEL} {{organization_id: $organization_id}})"
            f"-[r]->(b:{GRAPH_NODE_LABEL} {{organization_id: $organization_id}}) "
            "RETURN count(r) AS total",
            {"organization_id": str(organization_id)},
        )
        return int(result.scalar("total", 0) or 0)

    async def delete_relationship(
        self,
        organization_id: UUID,
        *,
        from_key: str,
        to_key: str,
        relationship_type: RelationshipType | str,
    ) -> bool:
        """Delete one relationship; returns whether it existed."""
        edge_type = validate_relationship_type(relationship_type)
        result = await self._client.write(
            f"MATCH (a:{GRAPH_NODE_LABEL} "
            "{key: $from_key, organization_id: $organization_id})"
            f"-[r:{edge_type}]->"
            f"(b:{GRAPH_NODE_LABEL} "
            "{key: $to_key, organization_id: $organization_id}) "
            "WITH r, count(r) AS found DELETE r RETURN found",
            {
                "from_key": from_key,
                "to_key": to_key,
                "organization_id": str(organization_id),
            },
        )
        return bool(result.records)

    # ---- traversal --------------------------------------------------

    async def traverse(
        self,
        organization_id: UUID,
        root_key: str,
        *,
        direction: TraversalDirection = TraversalDirection.BOTH,
        relationship_types: Sequence[RelationshipType | str] | None = None,
        node_types: Sequence[NodeType | str] | None = None,
        depth: int = 2,
        limit: int | None = None,
    ) -> Subgraph:
        """Walk outward from one node and assemble the subgraph.

        Neo4j returns one row per path, so the same node appears many
        times; nodes and relationships are both de-duplicated here rather
        than shipping a payload where one host is listed eight times.

        Raises:
            ValidationError: If any traversal parameter is invalid.
            DependencyError: If the graph is unreachable.
        """
        ceiling = validate_limit(limit or self._max_nodes, ceiling=_MAX_LIMIT)
        pattern = traversal_pattern(
            direction=direction,
            types=relationship_types,
            depth=depth,
            ceiling=self._max_depth,
        )
        # OPTIONAL MATCH, and the root returned on every row, for two
        # reasons that both bite: a subgraph whose edges name a node its
        # own node list omits is not renderable, and
        # ``Graph.from_subgraph`` deliberately drops edges pointing
        # outside the node set -- so every analysis run over a topology
        # would silently lose exactly the root's own edges. OPTIONAL is
        # what makes an isolated node return itself rather than nothing;
        # "this node has no neighbours" and "there is no such node" are
        # different answers and the caller needs to tell them apart.
        cypher = (
            f"MATCH (root:{GRAPH_NODE_LABEL} "
            "{key: $root_key, organization_id: $organization_id}) "
            f"OPTIONAL MATCH path = (root){pattern}"
            f"(other:{GRAPH_NODE_LABEL}{label_clause(node_types)} "
            "{organization_id: $organization_id}) "
            "WITH root, other, relationships(path) AS edges "
            "UNWIND coalesce(edges, [null]) AS edge "
            "RETURN DISTINCT properties(root) AS root_node, "
            "       properties(other) AS node, "
            "       startNode(edge).key AS from_key, "
            "       endNode(edge).key AS to_key, "
            "       type(edge) AS edge_type, "
            "       properties(edge) AS edge "
            "LIMIT $limit"
        )
        result = await self._client.read(
            cypher,
            {
                "root_key": root_key,
                "organization_id": str(organization_id),
                "limit": ceiling,
            },
            max_records=ceiling,
        )
        return self._assemble(root_key, result.records, truncated=result.truncated)

    async def neighbours(
        self,
        organization_id: UUID,
        node_key: str,
        *,
        direction: TraversalDirection = TraversalDirection.BOTH,
        relationship_types: Sequence[RelationshipType | str] | None = None,
        limit: int = 200,
    ) -> list[GraphNode]:
        """Directly adjacent nodes ("Neighbor Discovery")."""
        safe_limit = validate_limit(limit, ceiling=_MAX_LIMIT)
        pattern = traversal_pattern(
            direction=direction, types=relationship_types, ceiling=self._max_depth
        )
        cypher = (
            f"MATCH (a:{GRAPH_NODE_LABEL} "
            "{key: $node_key, organization_id: $organization_id})"
            f"{pattern}(n:{GRAPH_NODE_LABEL} "
            "{organization_id: $organization_id}) "
            f"RETURN DISTINCT {_NODE_RETURN} LIMIT $limit"
        )
        result = await self._client.read(
            cypher,
            {
                "node_key": node_key,
                "organization_id": str(organization_id),
                "limit": safe_limit,
            },
        )
        return [GraphNode.from_record(row.get("node", {})) for row in result.records]

    async def shortest_path(
        self,
        organization_id: UUID,
        *,
        from_key: str,
        to_key: str,
        relationship_types: Sequence[RelationshipType | str] | None = None,
        max_depth: int = 6,
    ) -> Subgraph:
        """The shortest path between two nodes ("Shortest Path").

        Returns an empty subgraph when no path exists -- that is a real
        answer ("these are not connected"), not an error.
        """
        safe_depth = validate_depth(max_depth, ceiling=self._max_depth)
        types = validate_relationship_types(relationship_types)
        edge_filter = (":" + "|".join(types)) if types else ""
        cypher = (
            f"MATCH (a:{GRAPH_NODE_LABEL} "
            "{key: $from_key, organization_id: $organization_id}), "
            f"(b:{GRAPH_NODE_LABEL} "
            "{key: $to_key, organization_id: $organization_id}) "
            f"MATCH path = shortestPath((a)-[r{edge_filter}*1..{safe_depth}]-(b)) "
            "UNWIND nodes(path) AS n "
            "WITH path, collect(properties(n)) AS path_nodes "
            "UNWIND relationships(path) AS edge "
            "RETURN path_nodes, startNode(edge).key AS from_key, "
            "       endNode(edge).key AS to_key, type(edge) AS edge_type, "
            "       properties(edge) AS edge"
        )
        result = await self._client.read(
            cypher,
            {
                "from_key": from_key,
                "to_key": to_key,
                "organization_id": str(organization_id),
            },
        )
        subgraph = Subgraph(root_key=from_key)
        seen: set[str] = set()
        for row in result.records:
            for raw in row.get("path_nodes") or []:
                node = GraphNode.from_record(raw)
                if node.key and node.key not in seen:
                    seen.add(node.key)
                    subgraph.nodes.append(node)
            subgraph.relationships.append(_edge_from_row(row))
        return subgraph

    async def degrees(
        self,
        organization_id: UUID,
        *,
        relationship_types: Sequence[RelationshipType | str] | None = None,
        limit: int = 5_000,
    ) -> dict[str, int]:
        """Every node's degree, keyed by node key ("Degree Centrality").

        Counted in Cypher rather than by loading the graph and counting
        in Python: the whole point of asking the database is that it can
        do this without materialising every edge in this process.
        """
        safe_limit = validate_limit(limit, ceiling=_MAX_LIMIT)
        types = validate_relationship_types(relationship_types)
        edge_filter = (":" + "|".join(types)) if types else ""
        cypher = (
            f"MATCH (n:{GRAPH_NODE_LABEL} {{organization_id: $organization_id}}) "
            f"OPTIONAL MATCH (n)-[r{edge_filter}]-"
            f"(m:{GRAPH_NODE_LABEL} {{organization_id: $organization_id}}) "
            "RETURN n.key AS key, count(r) AS degree "
            "ORDER BY degree DESC LIMIT $limit"
        )
        result = await self._client.read(
            cypher,
            {"organization_id": str(organization_id), "limit": safe_limit},
        )
        return {
            str(row.get("key")): int(row.get("degree") or 0)
            for row in result.records
            if row.get("key")
        }

    async def type_counts(self, organization_id: UUID) -> dict[str, int]:
        """How many nodes of each type an organization has."""
        result = await self._client.read(
            f"MATCH (n:{GRAPH_NODE_LABEL} {{organization_id: $organization_id}}) "
            "RETURN n.node_type AS node_type, count(n) AS total "
            "ORDER BY total DESC",
            {"organization_id": str(organization_id)},
        )
        return {
            str(row.get("node_type")): int(row.get("total") or 0)
            for row in result.records
            if row.get("node_type")
        }

    async def relationship_type_counts(self, organization_id: UUID) -> dict[str, int]:
        """How many relationships of each type an organization has."""
        result = await self._client.read(
            f"MATCH (a:{GRAPH_NODE_LABEL} {{organization_id: $organization_id}})"
            f"-[r]->(b:{GRAPH_NODE_LABEL} {{organization_id: $organization_id}}) "
            "RETURN type(r) AS edge_type, count(r) AS total ORDER BY total DESC",
            {"organization_id": str(organization_id)},
        )
        return {
            str(row.get("edge_type")): int(row.get("total") or 0)
            for row in result.records
            if row.get("edge_type")
        }

    async def orphan_keys(self, organization_id: UUID, *, limit: int = 500) -> list[str]:
        """Nodes with no relationships at all.

        Almost always a synchronization bug rather than a fact about the
        estate, which is why the figure is surfaced separately rather
        than buried in the node count.
        """
        safe_limit = validate_limit(limit, ceiling=_MAX_LIMIT)
        result = await self._client.read(
            f"MATCH (n:{GRAPH_NODE_LABEL} {{organization_id: $organization_id}}) "
            "WHERE NOT (n)--() RETURN n.key AS key LIMIT $limit",
            {"organization_id": str(organization_id), "limit": safe_limit},
        )
        return [str(row.get("key")) for row in result.records if row.get("key")]

    async def purge_organization(self, organization_id: UUID) -> int:
        """Delete every node in one organization; returns how many.

        Exists for snapshot restore and for test teardown. Scoped to one
        organization by parameter, never a bare ``MATCH (n) DETACH
        DELETE n`` -- the eight characters that empty a shared graph.
        """
        result = await self._client.write(
            f"MATCH (n:{GRAPH_NODE_LABEL} {{organization_id: $organization_id}}) "
            "WITH n, count(n) AS found DETACH DELETE n RETURN count(found) AS deleted",
            {"organization_id": str(organization_id)},
        )
        return int(result.scalar("deleted", 0) or 0)

    @staticmethod
    def _assemble(root_key: str, records: list[dict[str, Any]], *, truncated: bool) -> Subgraph:
        """De-duplicate traversal rows into a subgraph.

        The root goes in first, so it leads the node list rather than
        appearing wherever the traversal happened to reach it.
        """
        subgraph = Subgraph(root_key=root_key, truncated=truncated)
        seen_nodes: set[str] = set()
        seen_edges: set[str] = set()
        for row in records:
            root = GraphNode.from_record(row.get("root_node") or {})
            if root.key and root.key not in seen_nodes:
                seen_nodes.add(root.key)
                subgraph.nodes.append(root)
            node = GraphNode.from_record(row.get("node") or {})
            if node.key and node.key not in seen_nodes:
                seen_nodes.add(node.key)
                subgraph.nodes.append(node)
            edge = _edge_from_row(row)
            if edge.from_key and edge.to_key and edge.relationship_key not in seen_edges:
                seen_edges.add(edge.relationship_key)
                subgraph.relationships.append(edge)
        return subgraph


def _edge_from_row(row: dict[str, Any]) -> GraphRelationship:
    """Build a relationship from a row carrying its endpoints and type."""
    return GraphRelationship.from_record(
        row.get("edge", {}),
        from_key=str(row.get("from_key") or ""),
        to_key=str(row.get("to_key") or ""),
        relationship_type=str(row.get("edge_type") or RelationshipType.CUSTOM_RELATIONSHIP),
    )


__all__ = ["GraphRepository"]
