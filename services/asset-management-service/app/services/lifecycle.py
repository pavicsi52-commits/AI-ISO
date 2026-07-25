"""Lifecycle actions and audit trail.

Per docs/038 "LIFECYCLE MANAGEMENT" "Support": Provision, Operate,
Maintain, Upgrade, Reassign, Retire, Archive, Dispose, Lifecycle Audit.
Day-to-day lifecycle transitions flow through
:meth:`~app.services.managed_asset.ManagedAssetService.update`
(``PATCH``/``PUT /assets/{id}``, which already publishes
``LifecycleChanged`` and records history via :meth:`record_change`);
this service additionally owns the two lifecycle actions that are more
than a field update -- Retire and Dispose -- since each has its own
dedicated record (:class:`~app.models.asset_retirement.AssetRetirement`)
and event (``AssetRetired``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared_core.events.base import DomainEvent
from shared_core.exceptions.not_found import NotFoundError

from app.events.asset_events import AssetRetiredEvent, LifecycleChangedEvent
from app.models.asset_change_history import AssetChangeHistoryEntry
from app.models.asset_retirement import AssetRetirement
from app.models.enums import LifecycleState, ManagedAssetStatus
from app.repositories.asset_change_history import AssetChangeHistoryRepository
from app.repositories.asset_retirement import AssetRetirementRepository
from app.repositories.managed_asset import ManagedAssetRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]


class LifecycleService:
    """Records lifecycle change history and performs retire/dispose actions."""

    def __init__(
        self,
        managed_assets: ManagedAssetRepository,
        change_history: AssetChangeHistoryRepository,
        retirements: AssetRetirementRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._managed_assets = managed_assets
        self._change_history = change_history
        self._retirements = retirements
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def record_change(
        self,
        managed_asset_id: UUID,
        *,
        organization_id: UUID,
        actor_id: UUID | None,
        event_type: str,
        detail: dict[str, Any],
    ) -> AssetChangeHistoryEntry:
        """Record one narrative lifecycle timeline entry ("Lifecycle Audit")."""
        return await self._change_history.create(
            AssetChangeHistoryEntry(
                managed_asset_id=managed_asset_id,
                organization_id=organization_id,
                actor_id=actor_id,
                event_type=event_type,
                detail=detail,
            )
        )

    async def list_history(self, managed_asset_id: UUID) -> list[AssetChangeHistoryEntry]:
        """Every narrative lifecycle timeline entry for *managed_asset_id*, newest first."""
        return await self._change_history.list_for_managed_asset(managed_asset_id)

    async def get_retirement(self, managed_asset_id: UUID) -> AssetRetirement | None:
        """Return *managed_asset_id*'s retirement record, or ``None``."""
        return await self._retirements.get_for_managed_asset(managed_asset_id)

    async def retire(
        self, managed_asset_id: UUID, *, actor_id: UUID | None, reason: str | None
    ) -> AssetRetirement:
        """Retire a managed asset ("Retire")."""
        managed_asset = await self._managed_assets.require_by_id(managed_asset_id)
        now = datetime.now(UTC)
        managed_asset.status = ManagedAssetStatus.RETIRED
        managed_asset.lifecycle_state = LifecycleState.RETIRED
        managed_asset.retirement_date = now

        retirement = await self._retirements.get_for_managed_asset(managed_asset_id)
        if retirement is None:
            retirement = await self._retirements.create(
                AssetRetirement(
                    managed_asset_id=managed_asset_id,
                    organization_id=managed_asset.organization_id,
                    retired_at=now,
                    retired_by=actor_id,
                    reason=reason,
                )
            )
        else:
            retirement.retired_at = now
            retirement.retired_by = actor_id
            retirement.reason = reason

        await self.record_change(
            managed_asset_id,
            organization_id=managed_asset.organization_id,
            actor_id=actor_id,
            event_type="retired",
            detail={"reason": reason or ""},
        )
        await self._publish(
            AssetRetiredEvent(
                source_service="asset-management-service",
                payload={"managed_asset_id": str(managed_asset_id)},
            )
        )
        await self._publish(
            LifecycleChangedEvent(
                source_service="asset-management-service",
                payload={
                    "managed_asset_id": str(managed_asset_id),
                    "to": str(LifecycleState.RETIRED),
                },
            )
        )
        return retirement

    async def dispose(
        self,
        managed_asset_id: UUID,
        *,
        actor_id: UUID | None,
        disposal_method: str | None,
        residual_value_realized: float | None,
    ) -> AssetRetirement:
        """Dispose of a retired managed asset ("Dispose").

        Raises:
            NotFoundError: If *managed_asset_id* has never been retired.
        """
        retirement = await self._retirements.get_for_managed_asset(managed_asset_id)
        if retirement is None:
            raise NotFoundError(f"Managed asset '{managed_asset_id}' has not been retired yet.")
        managed_asset = await self._managed_assets.require_by_id(managed_asset_id)
        now = datetime.now(UTC)

        managed_asset.status = ManagedAssetStatus.DISPOSED
        managed_asset.lifecycle_state = LifecycleState.DISPOSED
        retirement.disposed_at = now
        retirement.disposal_method = disposal_method
        retirement.residual_value_realized = residual_value_realized

        await self.record_change(
            managed_asset_id,
            organization_id=managed_asset.organization_id,
            actor_id=actor_id,
            event_type="disposed",
            detail={"disposal_method": disposal_method or ""},
        )
        await self._publish(
            LifecycleChangedEvent(
                source_service="asset-management-service",
                payload={
                    "managed_asset_id": str(managed_asset_id),
                    "to": str(LifecycleState.DISPOSED),
                },
            )
        )
        return retirement


__all__ = ["LifecycleService"]
