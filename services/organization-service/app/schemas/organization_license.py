"""Request/response schemas for ``/organizations/{id}/licenses``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import LicenseStatus


class OrganizationLicenseUpdateRequest(BaseModel):
    """Body of ``PUT /organizations/{id}/licenses``."""

    license_type: str = Field(default="standard", max_length=64)
    license_key: str = Field(min_length=1, max_length=255)
    seat_count: int = Field(default=1, ge=1)
    expires_at: datetime | None = None
    grace_period_days: int = Field(default=14, ge=0)


class OrganizationLicenseResponse(BaseModel):
    """One organization's license, in full."""

    id: UUID
    organization_id: UUID
    license_type: str
    license_key: str
    seat_count: int
    consumed_seats: int
    status: LicenseStatus
    activated_at: datetime | None
    expires_at: datetime | None
    grace_period_days: int
    created_at: datetime
    updated_at: datetime


__all__ = ["OrganizationLicenseResponse", "OrganizationLicenseUpdateRequest"]
