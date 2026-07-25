"""Request/response schemas for ``/assets/{id}/warranty``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import RenewalStatus


class AssetWarrantyUpdateRequest(BaseModel):
    """Body of ``PUT /assets/{id}/warranty``."""

    provider: str = Field(min_length=1, max_length=255)
    warranty_number: str | None = None
    coverage: str | None = None
    start_date: datetime
    end_date: datetime
    renewal_status: RenewalStatus = RenewalStatus.NOT_RENEWED


class AssetWarrantyResponse(BaseModel):
    """One warranty coverage period."""

    id: UUID
    managed_asset_id: UUID
    provider: str
    warranty_number: str | None
    coverage: str | None
    start_date: datetime
    end_date: datetime
    expiration_alert_sent: bool
    renewal_status: RenewalStatus
    claims: list[dict[str, Any]]


__all__ = ["AssetWarrantyResponse", "AssetWarrantyUpdateRequest"]
