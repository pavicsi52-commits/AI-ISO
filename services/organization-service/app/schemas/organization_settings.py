"""Request/response schemas for ``/organizations/{id}/settings``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class OrganizationSettingsUpdateRequest(BaseModel):
    """Body of ``PUT /organizations/{id}/settings``."""

    password_policy: dict[str, Any] = Field(default_factory=dict)
    mfa_enforced: bool = False
    allowed_domains: list[str] = Field(default_factory=list)
    default_language: str = "en"
    default_timezone: str = "UTC"
    session_timeout_minutes: int = Field(default=60, ge=1)
    data_retention_days: int = Field(default=365, ge=1)
    storage_policy: dict[str, Any] = Field(default_factory=dict)
    notification_policy: dict[str, Any] = Field(default_factory=dict)


class OrganizationSettingsResponse(BaseModel):
    """One organization's settings, in full."""

    id: UUID
    organization_id: UUID
    password_policy: dict[str, Any]
    mfa_enforced: bool
    allowed_domains: list[str]
    default_language: str
    default_timezone: str
    session_timeout_minutes: int
    data_retention_days: int
    storage_policy: dict[str, Any]
    notification_policy: dict[str, Any]
    created_at: datetime
    updated_at: datetime


__all__ = ["OrganizationSettingsResponse", "OrganizationSettingsUpdateRequest"]
