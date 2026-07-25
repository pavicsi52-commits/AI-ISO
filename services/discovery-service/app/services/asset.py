"""Discovered-asset recording and Inventory Service synchronization."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from shared_core.events.base import DomainEvent
from shared_core.exceptions.dependency import DependencyError

from app.discovery.inventory_sync import InventorySyncClient
from app.events.discovery_events import AssetDiscoveredEvent, AssetUpdatedEvent
from app.models.discovery_asset import DiscoveryAsset
from app.models.enums import AssetClassification, SyncStatus
from app.repositories.discovery_asset import DiscoveryAssetRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]
_SOURCE_SERVICE = "discovery-service"


class DiscoveryAssetService:
    """Records discovered assets and reconciles them into the Inventory Service."""

    def __init__(
        self,
        assets: DiscoveryAssetRepository,
        inventory_sync: InventorySyncClient,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._assets = assets
        self._inventory_sync = inventory_sync
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def list_for_job(self, job_id: UUID) -> list[DiscoveryAsset]:
        """Every asset discovered by *job_id*."""
        return await self._assets.list_for_job(job_id)

    async def list_for_org(self, organization_id: UUID) -> list[DiscoveryAsset]:
        """Every discovered asset for *organization_id*."""
        return await self._assets.list_for_org(organization_id)

    async def record(
        self,
        job_id: UUID,
        result_id: UUID,
        *,
        organization_id: UUID,
        name: str,
        asset_type: str,
        classification: AssetClassification,
        fingerprint: dict[str, Any],
    ) -> DiscoveryAsset:
        """Record one discovered asset (not yet synchronized)."""
        asset = await self._assets.create(
            DiscoveryAsset(
                job_id=job_id,
                result_id=result_id,
                organization_id=organization_id,
                name=name,
                asset_type=asset_type,
                classification=classification,
                fingerprint=fingerprint,
            )
        )
        await self._publish(
            AssetDiscoveredEvent(
                source_service=_SOURCE_SERVICE,
                organization_id=organization_id,
                payload={"asset_id": str(asset.id), "job_id": str(job_id), "name": name},
            )
        )
        return asset

    async def sync_to_inventory(
        self,
        asset: DiscoveryAsset,
        *,
        organization_id: UUID,
        caller_token: str,
        identifiers: dict[str, str | None],
    ) -> DiscoveryAsset:
        """Reconcile *asset* into the Inventory Service ("Create Assets",
        "Update Assets", "Conflict Detection", "Asset Reconciliation").

        Never raises on a synchronization failure -- ``sync_status`` is
        set to ``FAILED`` instead, so one asset's sync problem never
        aborts the rest of a job's processing.
        """
        try:
            inventory_asset_id, created = await self._inventory_sync.sync_asset(
                asset,
                organization_id=organization_id,
                caller_token=caller_token,
                identifiers=identifiers,
            )
        except DependencyError:
            asset.sync_status = SyncStatus.FAILED
            return asset

        asset.synced_to_inventory = True
        asset.sync_status = SyncStatus.SYNCED
        asset.inventory_asset_id = inventory_asset_id
        if not created:
            await self._publish(
                AssetUpdatedEvent(
                    source_service=_SOURCE_SERVICE,
                    organization_id=organization_id,
                    payload={
                        "asset_id": str(asset.id),
                        "inventory_asset_id": str(inventory_asset_id),
                    },
                )
            )
        return asset


__all__ = ["DiscoveryAssetService"]
