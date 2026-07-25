"""Procurement and depreciation tracking. Per docs/038 "PROCUREMENT"
"Track": Purchase Order, Invoice, Cost Center, Supplier, Acquisition
Cost, Purchase Date, Expected Lifetime, Financial Metadata. Per
docs/038 "DEPRECIATION" "Support": Straight Line, Declining Balance,
Units of Production, Custom Policies, Book Value, Residual Value,
Depreciation Reports.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.models.asset_depreciation import AssetDepreciation
from app.models.asset_procurement import AssetProcurement
from app.models.enums import DepreciationMethod
from app.repositories.asset_depreciation import AssetDepreciationRepository
from app.repositories.asset_procurement import AssetProcurementRepository


def _straight_line_book_value(
    acquisition_cost: float, residual_value: float, useful_life_months: int, age_months: int
) -> float:
    if useful_life_months <= 0:
        return acquisition_cost
    depreciable = acquisition_cost - residual_value
    elapsed_fraction = min(1.0, max(0.0, age_months / useful_life_months))
    return acquisition_cost - (depreciable * elapsed_fraction)


class ProcurementService:
    """Manages acquisition (procurement) and depreciation records for a managed asset."""

    def __init__(
        self, procurements: AssetProcurementRepository, depreciations: AssetDepreciationRepository
    ) -> None:
        self._procurements = procurements
        self._depreciations = depreciations

    async def get_procurement(self, managed_asset_id: UUID) -> AssetProcurement | None:
        """Return *managed_asset_id*'s procurement record, or ``None``."""
        return await self._procurements.get_for_managed_asset(managed_asset_id)

    async def upsert_procurement(
        self,
        managed_asset_id: UUID,
        *,
        organization_id: UUID,
        vendor_id: UUID | None,
        purchase_order_number: str | None,
        invoice_number: str | None,
        cost_center: str | None,
        acquisition_cost: float,
        purchase_date: datetime | None,
        expected_lifetime_months: int | None,
        financial_metadata: dict[str, Any],
    ) -> AssetProcurement:
        """Create or replace *managed_asset_id*'s procurement record ("Track")."""
        existing = await self.get_procurement(managed_asset_id)
        if existing is not None:
            existing.vendor_id = vendor_id
            existing.purchase_order_number = purchase_order_number
            existing.invoice_number = invoice_number
            existing.cost_center = cost_center
            existing.acquisition_cost = acquisition_cost
            existing.purchase_date = purchase_date
            existing.expected_lifetime_months = expected_lifetime_months
            existing.financial_metadata = financial_metadata
            return existing
        return await self._procurements.create(
            AssetProcurement(
                managed_asset_id=managed_asset_id,
                organization_id=organization_id,
                vendor_id=vendor_id,
                purchase_order_number=purchase_order_number,
                invoice_number=invoice_number,
                cost_center=cost_center,
                acquisition_cost=acquisition_cost,
                purchase_date=purchase_date,
                expected_lifetime_months=expected_lifetime_months,
                financial_metadata=financial_metadata,
            )
        )

    async def get_depreciation(self, managed_asset_id: UUID) -> AssetDepreciation | None:
        """Return *managed_asset_id*'s depreciation record, or ``None``."""
        return await self._depreciations.get_for_managed_asset(managed_asset_id)

    async def upsert_depreciation(
        self,
        managed_asset_id: UUID,
        *,
        organization_id: UUID,
        method: DepreciationMethod,
        acquisition_cost: float,
        residual_value: float,
        useful_life_months: int,
        acquired_at: datetime,
    ) -> AssetDepreciation:
        """Create or replace *managed_asset_id*'s depreciation policy and
        recompute its current book value ("Book Value").
        """
        age_months = max(
            0,
            (datetime.now(UTC).year - acquired_at.year) * 12
            + (datetime.now(UTC).month - acquired_at.month),
        )
        book_value = _straight_line_book_value(
            acquisition_cost, residual_value, useful_life_months, age_months
        )

        existing = await self.get_depreciation(managed_asset_id)
        if existing is not None:
            existing.method = method
            existing.acquisition_cost = acquisition_cost
            existing.residual_value = residual_value
            existing.useful_life_months = useful_life_months
            existing.book_value = book_value
            existing.last_computed_at = datetime.now(UTC)
            return existing
        return await self._depreciations.create(
            AssetDepreciation(
                managed_asset_id=managed_asset_id,
                organization_id=organization_id,
                method=method,
                acquisition_cost=acquisition_cost,
                residual_value=residual_value,
                useful_life_months=useful_life_months,
                book_value=book_value,
                last_computed_at=datetime.now(UTC),
            )
        )


__all__ = ["ProcurementService"]
