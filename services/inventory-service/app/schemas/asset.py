"""Request/response schemas for ``/inventory/assets``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import AssetStatus, AssetType, Criticality, HealthStatus, LifecycleState


class AssetCreateRequest(BaseModel):
    """Body of ``POST /inventory/assets``."""

    organization_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    display_name: str | None = None
    hostname: str | None = None
    fqdn: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    serial_number: str | None = None
    vendor: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    firmware_version: str | None = None
    operating_system: str | None = None
    architecture: str | None = None
    environment: str | None = None
    asset_type: AssetType
    category_id: UUID | None = None
    class_id: UUID | None = None
    location_id: UUID | None = None
    owner_id: UUID | None = None
    criticality: Criticality = Criticality.MEDIUM
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class AssetUpdateRequest(BaseModel):
    """Body of ``PUT /inventory/assets/{id}``."""

    name: str = Field(min_length=1, max_length=255)
    display_name: str | None = None
    hostname: str | None = None
    fqdn: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    serial_number: str | None = None
    vendor: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    firmware_version: str | None = None
    operating_system: str | None = None
    architecture: str | None = None
    environment: str | None = None
    category_id: UUID | None = None
    class_id: UUID | None = None
    location_id: UUID | None = None
    owner_id: UUID | None = None
    status: AssetStatus = AssetStatus.DISCOVERED
    health: HealthStatus = HealthStatus.UNKNOWN
    lifecycle_state: LifecycleState = LifecycleState.PLANNED
    criticality: Criticality = Criticality.MEDIUM
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssetPatchRequest(BaseModel):
    """Body of ``PATCH /inventory/assets/{id}`` -- every field optional,
    unlike ``PUT``'s full-replace semantics.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    display_name: str | None = None
    hostname: str | None = None
    fqdn: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    serial_number: str | None = None
    vendor: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    firmware_version: str | None = None
    operating_system: str | None = None
    architecture: str | None = None
    environment: str | None = None
    category_id: UUID | None = None
    class_id: UUID | None = None
    location_id: UUID | None = None
    owner_id: UUID | None = None
    status: AssetStatus | None = None
    health: HealthStatus | None = None
    lifecycle_state: LifecycleState | None = None
    criticality: Criticality | None = None
    metadata: dict[str, Any] | None = None


class AssetResponse(BaseModel):
    """One asset, in full."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    name: str
    display_name: str | None
    hostname: str | None
    fqdn: str | None
    ip_address: str | None
    mac_address: str | None
    serial_number: str | None
    vendor: str | None
    manufacturer: str | None
    model: str | None
    firmware_version: str | None
    operating_system: str | None
    architecture: str | None
    environment: str | None
    asset_type: AssetType
    category_id: UUID | None
    class_id: UUID | None
    location_id: UUID | None
    owner_id: UUID | None
    status: AssetStatus
    health: HealthStatus
    lifecycle_state: LifecycleState
    criticality: Criticality
    current_version: int
    metadata: dict[str, Any]
    tags: list[str]
    created_at: datetime
    updated_at: datetime


__all__ = [
    "AssetCreateRequest",
    "AssetPatchRequest",
    "AssetResponse",
    "AssetUpdateRequest",
]
