"""Asset lifecycle: the orchestrator.

Per docs/036 "ASSET MODEL"/"ASSET STATUS"/"AUDIT". Every mutation that
touches status/health/lifecycle_state/location/owner also records the
matching history entry and publishes the matching domain event, and
every create/delete keeps this asset's Neo4j graph node in sync.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any
from uuid import UUID

from shared_core.database.filtering import Filter
from shared_core.database.pagination import PaginatedResult
from shared_core.database.sorting import SortField
from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError

from app.events.inventory_events import (
    AssetCreatedEvent,
    AssetDeletedEvent,
    AssetHealthChangedEvent,
    AssetMovedEvent,
    AssetOwnerChangedEvent,
    AssetUpdatedEvent,
)
from app.models.asset import Asset
from app.models.enums import AssetStatus, AssetType, Criticality, HealthStatus, LifecycleState
from app.repositories.asset import AssetRepository
from app.services.audit import InventoryAuditService
from app.services.health_history import AssetHealthHistoryService
from app.services.history import AssetHistoryService
from app.services.lifecycle_history import AssetLifecycleHistoryService
from app.services.status_history import AssetStatusHistoryService
from app.services.tag import AssetTagService
from app.services.topology import TopologyService
from app.services.version import AssetVersionService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]

_SNAPSHOT_FIELDS = (
    "name",
    "display_name",
    "hostname",
    "fqdn",
    "ip_address",
    "mac_address",
    "serial_number",
    "vendor",
    "manufacturer",
    "model",
    "firmware_version",
    "operating_system",
    "architecture",
    "environment",
    "status",
    "health",
    "lifecycle_state",
    "criticality",
    "metadata_",
)


def _snapshot(asset: Asset) -> dict[str, Any]:
    return {field: str(getattr(asset, field)) for field in _SNAPSHOT_FIELDS}


class AssetService:
    """Creates, reads, updates, and deletes assets."""

    def __init__(
        self,
        assets: AssetRepository,
        versions: AssetVersionService,
        tags: AssetTagService,
        status_history: AssetStatusHistoryService,
        health_history: AssetHealthHistoryService,
        lifecycle_history: AssetLifecycleHistoryService,
        history: AssetHistoryService,
        audit: InventoryAuditService,
        topology: TopologyService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._assets = assets
        self._versions = versions
        self._tags = tags
        self._status_history = status_history
        self._health_history = health_history
        self._lifecycle_history = lifecycle_history
        self._history = history
        self._audit = audit
        self._topology = topology
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, asset_id: UUID) -> Asset:
        """Return the asset identified by *asset_id*.

        Raises:
            NotFoundError: If no such asset exists.
        """
        return await self._assets.require_by_id(asset_id)

    async def list_for_org(self, organization_id: UUID) -> list[Asset]:
        """Every asset belonging to *organization_id*."""
        return await self._assets.list_for_org(organization_id)

    async def search(
        self,
        *,
        query: str | None,
        filters: Sequence[Filter] | None,
        sort_fields: Sequence[SortField] | None,
        page: int | None,
        page_size: int | None,
    ) -> PaginatedResult[Asset]:
        """Full-text search plus filter plus sort plus pagination ("SEARCH")."""
        return await self._assets.search_and_paginate(
            query=query, filters=filters, sort_fields=sort_fields, page=page, page_size=page_size
        )

    async def _reject_duplicate_identifiers(
        self,
        organization_id: UUID,
        *,
        hostname: str | None,
        serial_number: str | None,
        mac_address: str | None,
    ) -> None:
        """Raise :class:`ConflictError` if any of *hostname*,
        *serial_number*, or *mac_address* is already registered within
        *organization_id* ("Prevent duplicate identifiers").
        """
        if hostname and await self._assets.get_by_hostname(organization_id, hostname) is not None:
            raise ConflictError(f"Hostname {hostname!r} is already registered.")
        if (
            serial_number
            and await self._assets.get_by_serial_number(organization_id, serial_number) is not None
        ):
            raise ConflictError(f"Serial number {serial_number!r} is already registered.")
        if (
            mac_address
            and await self._assets.get_by_mac_address(organization_id, mac_address) is not None
        ):
            raise ConflictError(f"MAC address {mac_address!r} is already registered.")

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        name: str,
        display_name: str | None,
        hostname: str | None,
        fqdn: str | None,
        ip_address: str | None,
        mac_address: str | None,
        serial_number: str | None,
        vendor: str | None,
        manufacturer: str | None,
        model: str | None,
        firmware_version: str | None,
        operating_system: str | None,
        architecture: str | None,
        environment: str | None,
        asset_type: AssetType,
        category_id: UUID | None,
        class_id: UUID | None,
        location_id: UUID | None,
        owner_id: UUID | None,
        criticality: Criticality,
        metadata: dict[str, Any],
        tags: list[str],
        created_by: UUID | None,
    ) -> Asset:
        """Register a new asset ("Create").

        Raises:
            ConflictError: If *hostname*, *serial_number*, or
                *mac_address* is already registered within
                *organization_id* ("Prevent duplicate identifiers").
        """
        await self._reject_duplicate_identifiers(
            organization_id,
            hostname=hostname,
            serial_number=serial_number,
            mac_address=mac_address,
        )
        asset = await self._assets.create(
            Asset(
                organization_id=organization_id,
                project_id=project_id,
                name=name,
                display_name=display_name,
                hostname=hostname,
                fqdn=fqdn,
                ip_address=ip_address,
                mac_address=mac_address,
                serial_number=serial_number,
                vendor=vendor,
                manufacturer=manufacturer,
                model=model,
                firmware_version=firmware_version,
                operating_system=operating_system,
                architecture=architecture,
                environment=environment,
                asset_type=asset_type,
                category_id=category_id,
                class_id=class_id,
                location_id=location_id,
                owner_id=owner_id,
                status=AssetStatus.DISCOVERED,
                health=HealthStatus.UNKNOWN,
                lifecycle_state=LifecycleState.PLANNED,
                criticality=criticality,
                current_version=1,
                metadata_=metadata,
            )
        )
        await self._versions.create_snapshot(
            asset.id,
            organization_id=organization_id,
            snapshot=_snapshot(asset),
            created_by=created_by,
        )
        for label in tags:
            await self._tags.assign(asset.id, organization_id=organization_id, label=label)
        await self._topology.sync_asset_node(
            asset.id, organization_id=organization_id, asset_type=asset_type.value, name=name
        )
        await self._history.record(
            asset.id,
            organization_id=organization_id,
            actor_id=created_by,
            event_type="created",
            detail={"name": name, "asset_type": asset_type.value},
        )
        await self._audit.record(
            asset.id,
            organization_id=organization_id,
            actor_id=created_by,
            action="create",
            after={"name": name, "asset_type": asset_type.value},
        )
        await self._publish(
            AssetCreatedEvent(
                source_service="inventory-service", payload={"asset_id": str(asset.id)}
            )
        )
        return asset

    async def update(
        self,
        asset_id: UUID,
        *,
        actor_id: UUID | None,
        name: str,
        display_name: str | None,
        hostname: str | None,
        fqdn: str | None,
        ip_address: str | None,
        mac_address: str | None,
        serial_number: str | None,
        vendor: str | None,
        manufacturer: str | None,
        model: str | None,
        firmware_version: str | None,
        operating_system: str | None,
        architecture: str | None,
        environment: str | None,
        category_id: UUID | None,
        class_id: UUID | None,
        location_id: UUID | None,
        owner_id: UUID | None,
        status: AssetStatus,
        health: HealthStatus,
        lifecycle_state: LifecycleState,
        criticality: Criticality,
        metadata: dict[str, Any],
    ) -> Asset:
        """Replace an asset's mutable fields ("Update"), recording history
        and events for every status/health/lifecycle/location/owner change.
        """
        asset = await self.get_by_id(asset_id)
        previous_status, previous_health = asset.status, asset.health
        previous_lifecycle, previous_location = asset.lifecycle_state, asset.location_id
        previous_owner = asset.owner_id

        asset.name = name
        asset.display_name = display_name
        asset.hostname = hostname
        asset.fqdn = fqdn
        asset.ip_address = ip_address
        asset.mac_address = mac_address
        asset.serial_number = serial_number
        asset.vendor = vendor
        asset.manufacturer = manufacturer
        asset.model = model
        asset.firmware_version = firmware_version
        asset.operating_system = operating_system
        asset.architecture = architecture
        asset.environment = environment
        asset.category_id = category_id
        asset.class_id = class_id
        asset.location_id = location_id
        asset.owner_id = owner_id
        asset.status = status
        asset.health = health
        asset.lifecycle_state = lifecycle_state
        asset.criticality = criticality
        asset.metadata_ = metadata
        asset.current_version += 1

        await self._versions.create_snapshot(
            asset_id,
            organization_id=asset.organization_id,
            snapshot=_snapshot(asset),
            created_by=actor_id,
        )

        if str(previous_status) != str(status):
            await self._status_history.record(
                asset_id,
                organization_id=asset.organization_id,
                previous_status=previous_status,
                new_status=status,
                changed_by=actor_id,
            )
        if str(previous_health) != str(health):
            await self._health_history.record(
                asset_id, organization_id=asset.organization_id, health_status=health
            )
            await self._publish(
                AssetHealthChangedEvent(
                    source_service="inventory-service", payload={"asset_id": str(asset_id)}
                )
            )
        if str(previous_lifecycle) != str(lifecycle_state):
            await self._lifecycle_history.record(
                asset_id,
                organization_id=asset.organization_id,
                previous_state=previous_lifecycle,
                new_state=lifecycle_state,
                transitioned_by=actor_id,
            )
        if previous_location != location_id:
            await self._publish(
                AssetMovedEvent(
                    source_service="inventory-service", payload={"asset_id": str(asset_id)}
                )
            )
        if previous_owner != owner_id:
            await self._publish(
                AssetOwnerChangedEvent(
                    source_service="inventory-service", payload={"asset_id": str(asset_id)}
                )
            )

        await self._audit.record(
            asset_id,
            organization_id=asset.organization_id,
            actor_id=actor_id,
            action="update",
            before={"name": name, "status": str(previous_status)},
            after={"name": name, "status": str(status)},
        )
        await self._publish(
            AssetUpdatedEvent(
                source_service="inventory-service", payload={"asset_id": str(asset_id)}
            )
        )
        return asset

    async def delete(self, asset_id: UUID, *, actor_id: UUID | None) -> None:
        """Soft-delete an asset, removing its Neo4j graph node too ("Deletion")."""
        asset = await self.get_by_id(asset_id)
        await self._assets.delete(asset_id)
        await self._topology.remove_asset_node(asset_id)
        await self._audit.record(
            asset_id, organization_id=asset.organization_id, actor_id=actor_id, action="delete"
        )
        await self._publish(
            AssetDeletedEvent(
                source_service="inventory-service", payload={"asset_id": str(asset_id)}
            )
        )


__all__ = ["AssetService"]
