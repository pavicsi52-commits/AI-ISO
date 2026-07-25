"""Discovered-relationship recording and Inventory Service/Neo4j
synchronization (the latter handled entirely by
``services/inventory-service``'s own ``AssetRelationshipService`` as a
side effect of the sync call this service's own
:meth:`DiscoveryRelationshipService.sync_to_inventory` makes -- this
service never touches Neo4j directly).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import UUID

from shared_core.events.base import DomainEvent
from shared_core.exceptions.dependency import DependencyError

from app.discovery.inventory_sync import InventorySyncClient
from app.events.discovery_events import RelationshipDiscoveredEvent
from app.models.discovery_asset import DiscoveryAsset
from app.models.discovery_relationship import DiscoveryRelationship
from app.models.enums import DiscoveryRelationshipType
from app.repositories.discovery_relationship import DiscoveryRelationshipRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]
_SOURCE_SERVICE = "discovery-service"


class DiscoveryRelationshipService:
    """Records discovered relationship edges and reconciles them into
    the Inventory Service.
    """

    def __init__(
        self,
        relationships: DiscoveryRelationshipRepository,
        inventory_sync: InventorySyncClient,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._relationships = relationships
        self._inventory_sync = inventory_sync
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def list_for_job(self, job_id: UUID) -> list[DiscoveryRelationship]:
        """Every relationship edge detected by *job_id*."""
        return await self._relationships.list_for_job(job_id)

    async def record(
        self,
        job_id: UUID,
        *,
        organization_id: UUID,
        source_discovery_asset_id: UUID,
        target_discovery_asset_id: UUID,
        relationship_type: DiscoveryRelationshipType,
    ) -> DiscoveryRelationship:
        """Record one detected relationship edge, if not already recorded.

        Raises:
            ConflictError: If this exact edge was already recorded for
                this job (handled by the caller, which checks first --
                see ``app/services/discovery_execution.py``).
        """
        relationship = await self._relationships.create(
            DiscoveryRelationship(
                job_id=job_id,
                organization_id=organization_id,
                source_discovery_asset_id=source_discovery_asset_id,
                target_discovery_asset_id=target_discovery_asset_id,
                relationship_type=relationship_type,
            )
        )
        await self._publish(
            RelationshipDiscoveredEvent(
                source_service=_SOURCE_SERVICE,
                organization_id=organization_id,
                payload={
                    "relationship_id": str(relationship.id),
                    "source_discovery_asset_id": str(source_discovery_asset_id),
                    "target_discovery_asset_id": str(target_discovery_asset_id),
                    "relationship_type": str(relationship_type),
                },
            )
        )
        return relationship

    async def get_by_edge(
        self,
        source_discovery_asset_id: UUID,
        target_discovery_asset_id: UUID,
        relationship_type: DiscoveryRelationshipType,
    ) -> DiscoveryRelationship | None:
        """Return the edge identified by *(source, target, type)*, or ``None``."""
        return await self._relationships.get_by_edge(
            source_discovery_asset_id, target_discovery_asset_id, relationship_type
        )

    async def sync_to_inventory(
        self,
        relationship: DiscoveryRelationship,
        *,
        organization_id: UUID,
        source_asset: DiscoveryAsset,
        target_asset: DiscoveryAsset,
        caller_token: str,
    ) -> DiscoveryRelationship:
        """Reconcile *relationship* into the Inventory Service, provided
        both endpoint assets have themselves already been synchronized.

        Never raises on a synchronization failure -- best-effort, the
        same discipline :class:`~app.services.asset.DiscoveryAssetService
        .sync_to_inventory` follows.
        """
        if source_asset.inventory_asset_id is None or target_asset.inventory_asset_id is None:
            return relationship
        try:
            await self._inventory_sync.sync_relationship(
                relationship,
                organization_id=organization_id,
                source_inventory_asset_id=source_asset.inventory_asset_id,
                target_inventory_asset_id=target_asset.inventory_asset_id,
                caller_token=caller_token,
            )
        except DependencyError:
            return relationship
        relationship.synced_to_inventory = True
        return relationship


__all__ = ["DiscoveryRelationshipService"]
