"""Request/response schemas for ``/assets``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import (
    ComplianceStatus,
    Criticality,
    LifecycleState,
    ManagedAssetStatus,
    OperationalHealth,
    WarrantyStatus,
)


class ManagedAssetCreateRequest(BaseModel):
    """Body of ``POST /assets``."""

    organization_id: UUID
    project_id: UUID | None = None
    inventory_asset_id: UUID
    business_name: str = Field(min_length=1, max_length=255)
    business_owner_id: UUID | None = None
    technical_owner_id: UUID | None = None
    support_team_id: UUID | None = None
    vendor_id: UUID | None = None
    criticality: Criticality = Criticality.MEDIUM
    acquisition_date: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)


class ManagedAssetUpdateRequest(BaseModel):
    """Body of ``PUT /assets/{id}``."""

    business_name: str = Field(min_length=1, max_length=255)
    business_owner_id: UUID | None = None
    technical_owner_id: UUID | None = None
    support_team_id: UUID | None = None
    vendor_id: UUID | None = None
    status: ManagedAssetStatus = ManagedAssetStatus.PLANNED
    lifecycle_state: LifecycleState = LifecycleState.PROVISIONING
    criticality: Criticality = Criticality.MEDIUM
    acquisition_date: datetime | None = None
    retirement_date: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)


class ManagedAssetPatchRequest(BaseModel):
    """Body of ``PATCH /assets/{id}`` -- every field optional, unlike
    ``PUT``'s full-replace semantics.
    """

    business_name: str | None = Field(default=None, min_length=1, max_length=255)
    business_owner_id: UUID | None = None
    technical_owner_id: UUID | None = None
    support_team_id: UUID | None = None
    vendor_id: UUID | None = None
    status: ManagedAssetStatus | None = None
    lifecycle_state: LifecycleState | None = None
    criticality: Criticality | None = None
    acquisition_date: datetime | None = None
    retirement_date: datetime | None = None
    metadata: dict[str, Any] | None = None
    tags: list[str] | None = None
    labels: dict[str, str] | None = None


class ManagedAssetResponse(BaseModel):
    """One managed asset, in full -- per docs/038 "MANAGED ASSET MODEL"."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    inventory_asset_id: UUID
    business_name: str
    business_owner_id: UUID | None
    technical_owner_id: UUID | None
    support_team_id: UUID | None
    vendor_id: UUID | None
    status: ManagedAssetStatus
    lifecycle_state: LifecycleState
    criticality: Criticality
    warranty_status: WarrantyStatus
    compliance_status: ComplianceStatus
    risk_score: float
    operational_health: OperationalHealth
    acquisition_date: datetime | None
    retirement_date: datetime | None
    metadata: dict[str, Any]
    tags: list[str]
    labels: dict[str, str]
    created_at: datetime
    updated_at: datetime


__all__ = [
    "ManagedAssetCreateRequest",
    "ManagedAssetPatchRequest",
    "ManagedAssetResponse",
    "ManagedAssetUpdateRequest",
]
