"""Node and relationship management -- the service layer over the graph.

Wraps :class:`~app.graph.repository.GraphRepository` with the things a
write needs beyond the Cypher: change history, domain events, and the
metadata row that makes a node a digital twin.

**Every write records what changed.** The change log is what makes
"why is this node different from yesterday?" answerable, and it lives in
PostgreSQL rather than as extra graph nodes because an append-only time
series is what a relational table is good at and what makes a graph
slower to traverse.

**Deleting a node deletes its metadata too.** Leaving the metadata row
behind would orphan it -- unreachable by every read path, since they all
join on a node key that no longer exists -- while still occupying the
unique constraint that stops the node being recreated cleanly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.logging.logger import get_logger

from app.events.graph_events import (
    SOURCE_SERVICE,
    GraphNodeCreatedEvent,
    GraphNodeUpdatedEvent,
    GraphRelationshipCreatedEvent,
    GraphRelationshipRemovedEvent,
)
from app.graph.entities import (
    GraphNode,
    GraphRelationship,
    NodeInput,
    RelationshipInput,
    Subgraph,
)
from app.graph.repository import GraphRepository
from app.models.enums import (
    ChangeAction,
    NodeType,
    RelationshipType,
    TraversalDirection,
)
from app.models.graph_change_history import GraphChangeHistory
from app.repositories.graph_change_history import GraphChangeHistoryRepository
from app.repositories.graph_metadata import GraphMetadataRepository
from app.types import EventPublisher

logger = get_logger("app.services.graph")


class GraphService:
    """Creates, reads, updates, and deletes graph entities."""

    def __init__(
        self,
        graph: GraphRepository,
        changes: GraphChangeHistoryRepository,
        metadata: GraphMetadataRepository,
        *,
        publish_event: EventPublisher,
    ) -> None:
        self._graph = graph
        self._changes = changes
        self._metadata = metadata
        self._publish_event = publish_event

    # ---- nodes -----------------------------------------------------

    async def list_nodes(
        self,
        organization_id: UUID,
        *,
        node_types: list[NodeType] | None = None,
        project_id: str | None = None,
        source: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[GraphNode]:
        """Nodes for one organization, filtered and paginated."""
        return await self._graph.list_nodes(
            organization_id,
            node_types=node_types,
            project_id=project_id,
            source=source,
            limit=limit,
            offset=offset,
        )

    async def get_node(self, organization_id: UUID, key: str) -> GraphNode:
        """One node by key.

        Raises:
            NotFoundError: If it does not exist in this organization.
        """
        return await self._graph.require_node(organization_id, key)

    async def create_node(
        self, organization_id: UUID, node: NodeInput, *, actor_id: UUID | None = None
    ) -> GraphNode:
        """Create or update one node.

        Idempotent by ``MERGE``, so this is genuinely an upsert. The
        event reflects which it was, because a subscriber reacting to a
        new node should not fire on every property change.

        Raises:
            ValidationError: If the node type is not a known label.
            DependencyError: If the graph is unreachable.
        """
        existed = await self._graph.get_node(organization_id, node.key) is not None
        stored = await self._graph.upsert_node(organization_id, node)

        await self._changes.create(
            GraphChangeHistory(
                organization_id=organization_id,
                action=ChangeAction.NODE_UPDATED if existed else ChangeAction.NODE_CREATED,
                node_key=stored.key,
                entity_type=stored.node_type,
                after={"name": stored.name, "node_type": stored.node_type},
                actor_id=actor_id,
                occurred_at=datetime.now(UTC),
            )
        )
        event = GraphNodeUpdatedEvent if existed else GraphNodeCreatedEvent
        await self._publish_event(
            event(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "node_key": stored.key,
                    "node_type": stored.node_type,
                },
            )
        )
        return stored

    async def delete_node(
        self, organization_id: UUID, key: str, *, actor_id: UUID | None = None
    ) -> bool:
        """Delete one node, its relationships, and its metadata.

        Returns whether it existed. The metadata row goes too: leaving it
        would orphan a row no read path can reach while still holding the
        unique constraint that stops the node being recreated cleanly.
        """
        node = await self._graph.get_node(organization_id, key)
        if node is None:
            return False

        removed = await self._graph.delete_node(organization_id, key)
        stored = await self._metadata.get_for_node(organization_id, key)
        if stored is not None:
            await self._metadata.purge(stored.id)

        await self._changes.create(
            GraphChangeHistory(
                organization_id=organization_id,
                action=ChangeAction.NODE_DELETED,
                node_key=key,
                entity_type=node.node_type,
                before={"name": node.name, "node_type": node.node_type},
                actor_id=actor_id,
                occurred_at=datetime.now(UTC),
            )
        )
        return removed

    # ---- relationships ---------------------------------------------

    async def list_relationships(
        self,
        organization_id: UUID,
        *,
        node_key: str | None = None,
        relationship_types: list[RelationshipType] | None = None,
        direction: TraversalDirection = TraversalDirection.BOTH,
        limit: int = 200,
    ) -> list[GraphRelationship]:
        """Relationships for one organization, optionally around one node."""
        return await self._graph.list_relationships(
            organization_id,
            node_key=node_key,
            relationship_types=relationship_types,
            direction=direction,
            limit=limit,
        )

    async def create_relationship(
        self,
        organization_id: UUID,
        relationship: RelationshipInput,
        *,
        actor_id: UUID | None = None,
    ) -> GraphRelationship:
        """Create or update one relationship.

        Raises:
            NotFoundError: If either endpoint is missing.
            ValidationError: If the type is unknown or it is a self-loop.
            DependencyError: If the graph is unreachable.
        """
        stored = await self._graph.upsert_relationship(organization_id, relationship)
        await self._changes.create(
            GraphChangeHistory(
                organization_id=organization_id,
                action=ChangeAction.RELATIONSHIP_CREATED,
                relationship_key=stored.relationship_key,
                entity_type=stored.relationship_type,
                after={
                    "from_key": stored.from_key,
                    "to_key": stored.to_key,
                    "weight": stored.weight,
                },
                actor_id=actor_id,
                occurred_at=datetime.now(UTC),
            )
        )
        await self._publish_event(
            GraphRelationshipCreatedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "relationship_key": stored.relationship_key,
                    "relationship_type": stored.relationship_type,
                },
            )
        )
        return stored

    async def delete_relationship(
        self,
        organization_id: UUID,
        *,
        from_key: str,
        to_key: str,
        relationship_type: RelationshipType,
        actor_id: UUID | None = None,
    ) -> bool:
        """Delete one relationship; returns whether it existed."""
        removed = await self._graph.delete_relationship(
            organization_id,
            from_key=from_key,
            to_key=to_key,
            relationship_type=relationship_type,
        )
        if not removed:
            return False

        relationship_key = f"{from_key}|{relationship_type}|{to_key}"
        await self._changes.create(
            GraphChangeHistory(
                organization_id=organization_id,
                action=ChangeAction.RELATIONSHIP_DELETED,
                relationship_key=relationship_key,
                entity_type=str(relationship_type),
                before={"from_key": from_key, "to_key": to_key},
                actor_id=actor_id,
                occurred_at=datetime.now(UTC),
            )
        )
        await self._publish_event(
            GraphRelationshipRemovedEvent(
                source_service=SOURCE_SERVICE,
                payload={
                    "organization_id": str(organization_id),
                    "relationship_key": relationship_key,
                    "relationship_type": str(relationship_type),
                },
            )
        )
        return True

    # ---- traversal --------------------------------------------------

    async def topology(
        self,
        organization_id: UUID,
        root_key: str,
        *,
        depth: int = 2,
        direction: TraversalDirection = TraversalDirection.BOTH,
        relationship_types: list[RelationshipType] | None = None,
        node_types: list[NodeType] | None = None,
    ) -> Subgraph:
        """The subgraph around one node ("TOPOLOGY").

        This is the endpoint the dashboard, monitoring, automation,
        validation, workflow, and AI-assistant services consume.

        Raises:
            NotFoundError: If the root does not exist.
            ValidationError: If the traversal parameters are invalid.
        """
        await self._graph.require_node(organization_id, root_key)
        return await self._graph.traverse(
            organization_id,
            root_key,
            direction=direction,
            relationship_types=relationship_types,
            node_types=node_types,
            depth=depth,
        )

    async def neighbours(
        self,
        organization_id: UUID,
        node_key: str,
        *,
        direction: TraversalDirection = TraversalDirection.BOTH,
        relationship_types: list[RelationshipType] | None = None,
        limit: int = 200,
    ) -> list[GraphNode]:
        """Directly adjacent nodes ("Neighbor Discovery")."""
        return await self._graph.neighbours(
            organization_id,
            node_key,
            direction=direction,
            relationship_types=relationship_types,
            limit=limit,
        )

    async def shortest_path(
        self,
        organization_id: UUID,
        *,
        from_key: str,
        to_key: str,
        relationship_types: list[RelationshipType] | None = None,
        max_depth: int = 6,
    ) -> Subgraph:
        """The shortest path between two nodes.

        An empty subgraph means "these are not connected", which is a
        real answer rather than a failure.
        """
        return await self._graph.shortest_path(
            organization_id,
            from_key=from_key,
            to_key=to_key,
            relationship_types=relationship_types,
            max_depth=max_depth,
        )

    async def history(
        self, organization_id: UUID, *, node_key: str | None = None, limit: int = 100
    ) -> list[GraphChangeHistory]:
        """What changed, organization-wide or for one node."""
        if node_key is not None:
            return await self._changes.list_for_node(organization_id, node_key, limit=limit)
        return await self._changes.list_for_org(organization_id, limit=limit)

    async def counts(self, organization_id: UUID) -> dict[str, Any]:
        """Node and relationship totals with their type breakdowns."""
        return {
            "node_count": await self._graph.count_nodes(organization_id),
            "relationship_count": await self._graph.count_relationships(organization_id),
            "node_type_counts": await self._graph.type_counts(organization_id),
            "relationship_type_counts": await self._graph.relationship_type_counts(organization_id),
        }


__all__ = ["GraphService"]
