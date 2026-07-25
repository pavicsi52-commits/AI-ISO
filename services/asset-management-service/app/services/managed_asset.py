"""Managed asset lifecycle: the orchestrator.

Per docs/038 "MANAGED ASSET MODEL"/"ASSET STATUS"/"AUDIT". Every create
records a change-history entry, an audit entry, and publishes
``ManagedAssetCreated``; every status/lifecycle transition on update
publishes ``LifecycleChanged``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from shared_core.database.filtering import Filter
from shared_core.database.pagination import PaginatedResult
from shared_core.database.sorting import SortField
from shared_core.events.base import DomainEvent
from shared_core.exceptions.conflict import ConflictError

from app.events.asset_events import LifecycleChangedEvent, ManagedAssetCreatedEvent
from app.models.enums import Criticality, LifecycleState, ManagedAssetStatus
from app.models.managed_asset import ManagedAsset
from app.repositories.managed_asset import ManagedAssetRepository
from app.services.audit import AssetAuditService
from app.services.lifecycle import LifecycleService

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class ManagedAssetService:
    """Creates, reads, updates, and deletes managed assets."""

    def __init__(
        self,
        managed_assets: ManagedAssetRepository,
        lifecycle: LifecycleService,
        audit: AssetAuditService,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._managed_assets = managed_assets
        self._lifecycle = lifecycle
        self._audit = audit
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def get_by_id(self, managed_asset_id: UUID) -> ManagedAsset:
        """Return the managed asset identified by *managed_asset_id*.

        Raises:
            NotFoundError: If no such managed asset exists.
        """
        return await self._managed_assets.require_by_id(managed_asset_id)

    async def get_by_inventory_asset_id(self, inventory_asset_id: UUID) -> ManagedAsset | None:
        """Return the managed asset governing *inventory_asset_id*, or ``None``."""
        return await self._managed_assets.get_by_inventory_asset_id(inventory_asset_id)

    async def list_for_org(self, organization_id: UUID) -> list[ManagedAsset]:
        """Every managed asset belonging to *organization_id*."""
        return await self._managed_assets.list_for_org(organization_id)

    async def search(
        self,
        *,
        query: str | None,
        filters: Sequence[Filter] | None,
        sort_fields: Sequence[SortField] | None,
        page: int | None,
        page_size: int | None,
    ) -> PaginatedResult[ManagedAsset]:
        """Full-text search plus filter plus sort plus pagination."""
        return await self._managed_assets.search_and_paginate(
            query=query, filters=filters, sort_fields=sort_fields, page=page, page_size=page_size
        )

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        inventory_asset_id: UUID,
        business_name: str,
        business_owner_id: UUID | None,
        technical_owner_id: UUID | None,
        support_team_id: UUID | None,
        vendor_id: UUID | None,
        criticality: Criticality,
        acquisition_date: datetime | None,
        metadata: dict[str, Any],
        tags: list[str],
        labels: dict[str, str],
        created_by: UUID | None,
    ) -> ManagedAsset:
        """Bring an inventoried asset under enterprise governance ("Create").

        Raises:
            ConflictError: If *inventory_asset_id* already has a managed asset.
        """
        if await self._managed_assets.get_by_inventory_asset_id(inventory_asset_id) is not None:
            raise ConflictError(
                f"Inventory asset {inventory_asset_id} is already under management."
            )
        managed_asset = await self._managed_assets.create(
            ManagedAsset(
                organization_id=organization_id,
                project_id=project_id,
                inventory_asset_id=inventory_asset_id,
                business_name=business_name,
                business_owner_id=business_owner_id,
                technical_owner_id=technical_owner_id,
                support_team_id=support_team_id,
                vendor_id=vendor_id,
                status=ManagedAssetStatus.PLANNED,
                lifecycle_state=LifecycleState.PROVISIONING,
                criticality=criticality,
                acquisition_date=acquisition_date,
                metadata_=metadata,
                tags=tags,
                labels=labels,
            )
        )
        await self._lifecycle.record_change(
            managed_asset.id,
            organization_id=organization_id,
            actor_id=created_by,
            event_type="created",
            detail={"business_name": business_name},
        )
        await self._audit.record(
            managed_asset.id,
            organization_id=organization_id,
            actor_id=created_by,
            action="create",
            after={"business_name": business_name},
        )
        await self._publish(
            ManagedAssetCreatedEvent(
                source_service="asset-management-service",
                payload={"managed_asset_id": str(managed_asset.id)},
            )
        )
        return managed_asset

    async def update(
        self,
        managed_asset_id: UUID,
        *,
        actor_id: UUID | None,
        business_name: str,
        business_owner_id: UUID | None,
        technical_owner_id: UUID | None,
        support_team_id: UUID | None,
        vendor_id: UUID | None,
        status: ManagedAssetStatus,
        lifecycle_state: LifecycleState,
        criticality: Criticality,
        acquisition_date: datetime | None,
        retirement_date: datetime | None,
        metadata: dict[str, Any],
        tags: list[str],
        labels: dict[str, str],
    ) -> ManagedAsset:
        """Replace a managed asset's mutable fields ("Update"), publishing
        ``LifecycleChanged`` when :attr:`~ManagedAsset.lifecycle_state`
        transitions.
        """
        managed_asset = await self.get_by_id(managed_asset_id)
        previous_lifecycle = managed_asset.lifecycle_state

        managed_asset.business_name = business_name
        managed_asset.business_owner_id = business_owner_id
        managed_asset.technical_owner_id = technical_owner_id
        managed_asset.support_team_id = support_team_id
        managed_asset.vendor_id = vendor_id
        managed_asset.status = status
        managed_asset.lifecycle_state = lifecycle_state
        managed_asset.criticality = criticality
        managed_asset.acquisition_date = acquisition_date
        managed_asset.retirement_date = retirement_date
        managed_asset.metadata_ = metadata
        managed_asset.tags = tags
        managed_asset.labels = labels

        if str(previous_lifecycle) != str(lifecycle_state):
            await self._lifecycle.record_change(
                managed_asset_id,
                organization_id=managed_asset.organization_id,
                actor_id=actor_id,
                event_type="lifecycle_changed",
                detail={"from": str(previous_lifecycle), "to": str(lifecycle_state)},
            )
            await self._publish(
                LifecycleChangedEvent(
                    source_service="asset-management-service",
                    payload={
                        "managed_asset_id": str(managed_asset_id),
                        "from": str(previous_lifecycle),
                        "to": str(lifecycle_state),
                    },
                )
            )

        await self._audit.record(
            managed_asset_id,
            organization_id=managed_asset.organization_id,
            actor_id=actor_id,
            action="update",
            before={"business_name": business_name, "lifecycle_state": str(previous_lifecycle)},
            after={"business_name": business_name, "lifecycle_state": str(lifecycle_state)},
        )
        return managed_asset

    async def delete(self, managed_asset_id: UUID, *, actor_id: UUID | None) -> None:
        """Soft-delete a managed asset ("Delete")."""
        managed_asset = await self.get_by_id(managed_asset_id)
        await self._managed_assets.delete(managed_asset_id)
        await self._audit.record(
            managed_asset_id,
            organization_id=managed_asset.organization_id,
            actor_id=actor_id,
            action="delete",
        )


__all__ = ["ManagedAssetService"]
