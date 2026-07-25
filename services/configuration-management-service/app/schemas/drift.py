"""Response/request schemas for ``GET /configurations/drift``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import DriftStatus, DriftType


class ConfigurationDriftReportRequest(BaseModel):
    """Body of ``POST /configurations/drift`` -- record a detected drift."""

    profile_id: UUID
    managed_asset_id: UUID
    drift_type: DriftType
    details: dict[str, Any] = Field(default_factory=dict)


class ConfigurationDriftResolveRequest(BaseModel):
    """Body of ``PATCH /configurations/drift/{id}`` -- resolve or ignore a drift."""

    status: DriftStatus
    resolved_by: UUID | None = None


class ConfigurationDriftResponse(BaseModel):
    """One detected drift instance between desired and actual state."""

    id: UUID
    profile_id: UUID
    managed_asset_id: UUID
    drift_type: DriftType
    status: DriftStatus
    detected_at: datetime
    details: dict[str, Any]
    resolved_at: datetime | None
    resolved_by: UUID | None


__all__ = [
    "ConfigurationDriftReportRequest",
    "ConfigurationDriftResolveRequest",
    "ConfigurationDriftResponse",
]
