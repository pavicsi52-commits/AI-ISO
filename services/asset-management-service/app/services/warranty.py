"""Warranty tracking. Per docs/038 "WARRANTY" "Track": Warranty
Provider, Warranty Number, Coverage, Start Date, End Date, Expiration
Alerts, Renewal Status, Warranty Claims.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from shared_core.events.base import DomainEvent
from shared_core.exceptions.not_found import NotFoundError

from app.events.asset_events import WarrantyExpiredEvent
from app.models.asset_warranty import AssetWarranty
from app.models.enums import RenewalStatus, WarrantyStatus
from app.repositories.asset_warranty import AssetWarrantyRepository
from app.repositories.managed_asset import ManagedAssetRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]

_EXPIRING_SOON_WINDOW_DAYS = 30


def _derive_status(end_date: datetime, *, now: datetime) -> WarrantyStatus:
    if end_date < now:
        return WarrantyStatus.EXPIRED
    if (end_date - now).days <= _EXPIRING_SOON_WINDOW_DAYS:
        return WarrantyStatus.EXPIRING_SOON
    return WarrantyStatus.ACTIVE


class WarrantyService:
    """Tracks warranty coverage periods for a managed asset."""

    def __init__(
        self,
        warranties: AssetWarrantyRepository,
        managed_assets: ManagedAssetRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._warranties = warranties
        self._managed_assets = managed_assets
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetWarranty]:
        """Every warranty period recorded for *managed_asset_id*, newest first."""
        return await self._warranties.list_for_managed_asset(managed_asset_id)

    async def get_current(self, managed_asset_id: UUID) -> AssetWarranty | None:
        """Return *managed_asset_id*'s current warranty period, or ``None``."""
        return await self._warranties.get_current_for_managed_asset(managed_asset_id)

    async def update(
        self,
        managed_asset_id: UUID,
        *,
        organization_id: UUID,
        provider: str,
        warranty_number: str | None,
        coverage: str | None,
        start_date: datetime,
        end_date: datetime,
        renewal_status: RenewalStatus,
    ) -> AssetWarranty:
        """Replace *managed_asset_id*'s current warranty period ("Track")."""
        current = await self.get_current(managed_asset_id)
        if current is not None and current.end_date == end_date:
            current.provider = provider
            current.warranty_number = warranty_number
            current.coverage = coverage
            current.start_date = start_date
            current.renewal_status = renewal_status
            warranty = current
        else:
            warranty = await self._warranties.create(
                AssetWarranty(
                    managed_asset_id=managed_asset_id,
                    organization_id=organization_id,
                    provider=provider,
                    warranty_number=warranty_number,
                    coverage=coverage,
                    start_date=start_date,
                    end_date=end_date,
                    renewal_status=renewal_status,
                )
            )

        managed_asset = await self._managed_assets.require_by_id(managed_asset_id)
        managed_asset.warranty_status = _derive_status(end_date, now=datetime.now(UTC))
        return warranty

    async def add_claim(
        self, managed_asset_id: UUID, *, description: str, outcome: str
    ) -> AssetWarranty:
        """Record a warranty claim against *managed_asset_id*'s current
        warranty period ("Warranty Claims").

        Raises:
            NotFoundError: If *managed_asset_id* has no current warranty period.
        """
        warranty = await self.get_current(managed_asset_id)
        if warranty is None:
            raise NotFoundError(
                f"Managed asset '{managed_asset_id}' has no current warranty period."
            )
        claim: dict[str, Any] = {
            "description": description,
            "outcome": outcome,
            "claimed_at": datetime.now(UTC).isoformat(),
        }
        warranty.claims = [*warranty.claims, claim]
        return warranty

    async def sweep_expiring(self, *, within_days: int = _EXPIRING_SOON_WINDOW_DAYS) -> int:
        """Publish ``WarrantyExpired`` for every warranty period ending
        within *within_days* that hasn't already alerted, marking each
        alerted ("Expiration Alerts"). Returns the number alerted.
        """
        cutoff = datetime.now(UTC) + timedelta(days=within_days)
        expiring = await self._warranties.list_expiring_before(cutoff)
        for warranty in expiring:
            warranty.expiration_alert_sent = True
            await self._publish(
                WarrantyExpiredEvent(
                    source_service="asset-management-service",
                    payload={"managed_asset_id": str(warranty.managed_asset_id)},
                )
            )
        return len(expiring)


__all__ = ["WarrantyService"]
