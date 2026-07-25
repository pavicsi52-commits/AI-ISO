"""Request/response schemas for ``/assets/{id}/maintenance`` and the
underlying maintenance-window/history records.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import MaintenanceStatus, MaintenanceType, MaintenanceWindowType


class AssetMaintenanceCreateRequest(BaseModel):
    """Body of ``POST /assets/{id}/maintenance``."""

    maintenance_type: MaintenanceType
    description: str = Field(min_length=1, max_length=2048)
    scheduled_at: datetime


class AssetMaintenanceResponse(BaseModel):
    """One maintenance activity."""

    id: UUID
    managed_asset_id: UUID
    maintenance_type: MaintenanceType
    status: MaintenanceStatus
    description: str
    scheduled_at: datetime
    completed_at: datetime | None
    approved_by: UUID | None
    approved_at: datetime | None


class AssetMaintenanceWindowResponse(BaseModel):
    """One planned downtime window."""

    id: UUID
    managed_asset_id: UUID
    window_type: MaintenanceWindowType
    starts_at: datetime
    ends_at: datetime
    recurrence_rule: str | None
    approved: bool
    notify: bool


class AssetMaintenanceHistoryResponse(BaseModel):
    """One maintenance timeline entry."""

    id: UUID
    managed_asset_id: UUID
    maintenance_id: UUID | None
    event_type: str
    detail: dict[str, object]
    occurred_at: datetime


__all__ = [
    "AssetMaintenanceCreateRequest",
    "AssetMaintenanceHistoryResponse",
    "AssetMaintenanceResponse",
    "AssetMaintenanceWindowResponse",
]
