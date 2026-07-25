"""Asset relationship management -- Postgres stays authoritative;
every create/delete is mirrored into Neo4j so topology traversal has a
graph to query. See ``app/models/asset_relationship.py``'s own
docstring for the dual-write rationale.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError

from app.events.inventory_events import RelationshipCreatedEvent, RelationshipDeletedEvent
from app.models.asset_relationship import AssetRelationship
from app.models.enums import RelationshipType
from app.repositories.asset_relationship import AssetRelationshipRepository
from app.services.topology import TopologyService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class AssetRelationshipService:
    """Creates, lists, and deletes relationship edges between assets."""

    def __init__(
        self,
        relationships: AssetRelationshipRepository,
        topology: TopologyService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._relationships = relationships
        self._topology = topology
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def list_for_asset(self, asset_id: UUID) -> list[AssetRelationship]:
        """Every relationship touching *asset_id*, as either source or target."""
        return await self._relationships.list_for_asset(asset_id)

    async def create(
        self,
        *,
        organization_id: UUID,
        source_asset_id: UUID,
        target_asset_id: UUID,
        relationship_type: RelationshipType,
        custom_label: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AssetRelationship:
        """Create a new relationship edge, mirrored into Neo4j.

        Raises:
            ConflictError: If this exact edge already exists.
        """
        if (
            await self._relationships.get_by_edge(
                source_asset_id, target_asset_id, relationship_type
            )
            is not None
        ):
            raise ConflictError(
                f"A {relationship_type.value!r} relationship from {source_asset_id} to "
                f"{target_asset_id} already exists."
            )
        relationship = await self._relationships.create(
            AssetRelationship(
                organization_id=organization_id,
                source_asset_id=source_asset_id,
                target_asset_id=target_asset_id,
                relationship_type=relationship_type,
                custom_label=custom_label,
                metadata_=metadata or {},
            )
        )
        await self._topology.sync_relationship(source_asset_id, target_asset_id, relationship_type)
        await self._publish(
            RelationshipCreatedEvent(
                source_service="inventory-service",
                payload={"relationship_id": str(relationship.id)},
            )
        )
        return relationship

    async def delete(self, relationship_id: UUID) -> None:
        """Delete a relationship edge, removing its mirror from Neo4j too.

        Raises:
            NotFoundError: If no such relationship exists.
        """
        relationship = await self._relationships.require_by_id(relationship_id)
        await self._relationships.delete(relationship_id)
        await self._topology.remove_relationship(
            relationship.source_asset_id,
            relationship.target_asset_id,
            relationship.relationship_type,
        )
        await self._publish(
            RelationshipDeletedEvent(
                source_service="inventory-service",
                payload={"relationship_id": str(relationship_id)},
            )
        )


__all__ = ["AssetRelationshipService"]
