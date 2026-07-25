"""Request/response schemas for ``/assets/{id}/contracts`` and the
underlying :class:`~app.models.asset_vendor.AssetVendor` registry.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ContractStatus, ContractType, RenewalStatus


class AssetContractCreateRequest(BaseModel):
    """Body of ``POST /assets/{id}/contracts``."""

    vendor_id: UUID | None = None
    contract_type: ContractType
    contract_number: str | None = None
    start_date: datetime
    end_date: datetime
    documents: list[dict[str, Any]] = Field(default_factory=list)


class AssetContractResponse(BaseModel):
    """One contract covering a managed asset."""

    id: UUID
    managed_asset_id: UUID
    vendor_id: UUID | None
    contract_type: ContractType
    status: ContractStatus
    contract_number: str | None
    start_date: datetime
    end_date: datetime
    renewal_status: RenewalStatus
    documents: list[dict[str, Any]]


class AssetVendorResponse(BaseModel):
    """One vendor/supplier."""

    id: UUID
    organization_id: UUID
    name: str
    contact_email: str | None
    contact_phone: str | None
    website: str | None
    notes: str | None


__all__ = ["AssetContractCreateRequest", "AssetContractResponse", "AssetVendorResponse"]
