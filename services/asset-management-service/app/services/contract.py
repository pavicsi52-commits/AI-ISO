"""Contract and vendor management. Per docs/038 "CONTRACT MANAGEMENT"
"Support": Support Contracts, Maintenance Contracts, License Contracts,
Vendor Contracts, Contract Expiration, Renewal Tracking, Documents,
Attachments.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from shared_core.events.base import DomainEvent

from app.events.asset_events import ContractExpiredEvent
from app.models.asset_contract import AssetContract
from app.models.asset_vendor import AssetVendor
from app.models.enums import ContractStatus, ContractType, RenewalStatus
from app.repositories.asset_contract import AssetContractRepository
from app.repositories.asset_vendor import AssetVendorRepository

EventPublisher = Callable[[DomainEvent], Awaitable[None]]

_EXPIRING_SOON_WINDOW_DAYS = 30


class ContractService:
    """Manages contracts and the vendor registry backing them."""

    def __init__(
        self,
        contracts: AssetContractRepository,
        vendors: AssetVendorRepository,
        *,
        publish_event: EventPublisher | None = None,
    ) -> None:
        self._contracts = contracts
        self._vendors = vendors
        self._publish_event = publish_event

    async def _publish(self, event: DomainEvent) -> None:
        if self._publish_event is not None:
            await self._publish_event(event)

    async def list_for_managed_asset(self, managed_asset_id: UUID) -> list[AssetContract]:
        """Every contract covering *managed_asset_id*, newest first."""
        return await self._contracts.list_for_managed_asset(managed_asset_id)

    async def create(
        self,
        managed_asset_id: UUID,
        *,
        organization_id: UUID,
        vendor_id: UUID | None,
        contract_type: ContractType,
        contract_number: str | None,
        start_date: datetime,
        end_date: datetime,
        documents: list[dict[str, Any]],
    ) -> AssetContract:
        """Add a contract covering *managed_asset_id* ("Support")."""
        return await self._contracts.create(
            AssetContract(
                managed_asset_id=managed_asset_id,
                organization_id=organization_id,
                vendor_id=vendor_id,
                contract_type=contract_type,
                status=ContractStatus.ACTIVE,
                contract_number=contract_number,
                start_date=start_date,
                end_date=end_date,
                renewal_status=RenewalStatus.NOT_RENEWED,
                documents=documents,
            )
        )

    async def list_vendors(self, organization_id: UUID) -> list[AssetVendor]:
        """Every vendor registered for *organization_id* ("Supplier")."""
        return await self._vendors.list_for_org(organization_id)

    async def get_or_create_vendor(
        self,
        organization_id: UUID,
        *,
        name: str,
        contact_email: str | None = None,
        contact_phone: str | None = None,
        website: str | None = None,
    ) -> AssetVendor:
        """Return *organization_id*'s vendor named *name*, creating it if new."""
        existing = await self._vendors.get_by_name(organization_id, name)
        if existing is not None:
            return existing
        return await self._vendors.create(
            AssetVendor(
                organization_id=organization_id,
                name=name,
                contact_email=contact_email,
                contact_phone=contact_phone,
                website=website,
            )
        )

    async def sweep_expiring(self, *, within_days: int = _EXPIRING_SOON_WINDOW_DAYS) -> int:
        """Publish ``ContractExpired`` for every contract ending within
        *within_days* ("Contract Expiration"). Returns the number alerted.
        """
        cutoff = datetime.now(UTC) + timedelta(days=within_days)
        expiring = await self._contracts.list_expiring_before(cutoff)
        for contract in expiring:
            contract.status = ContractStatus.EXPIRED
            await self._publish(
                ContractExpiredEvent(
                    source_service="asset-management-service",
                    payload={"managed_asset_id": str(contract.managed_asset_id)},
                )
            )
        return len(expiring)


__all__ = ["ContractService"]
