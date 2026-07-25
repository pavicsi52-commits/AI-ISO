"""Response schemas for :class:`~app.models.asset_procurement
.AssetProcurement` and :class:`~app.models.asset_depreciation
.AssetDepreciation` -- surfaced as part of a managed asset's financial
profile rather than through their own top-level REST resource, per
docs/038's own REST APIs list (which names no dedicated procurement/
depreciation path).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import DepreciationMethod


class AssetProcurementResponse(BaseModel):
    """One managed asset's procurement record."""

    id: UUID
    managed_asset_id: UUID
    vendor_id: UUID | None
    purchase_order_number: str | None
    invoice_number: str | None
    cost_center: str | None
    acquisition_cost: float
    purchase_date: datetime | None
    expected_lifetime_months: int | None
    financial_metadata: dict[str, Any]


class AssetDepreciationResponse(BaseModel):
    """One managed asset's depreciation policy and current book value."""

    id: UUID
    managed_asset_id: UUID
    method: DepreciationMethod
    acquisition_cost: float
    residual_value: float
    useful_life_months: int
    book_value: float
    last_computed_at: datetime | None


__all__ = ["AssetDepreciationResponse", "AssetProcurementResponse"]
