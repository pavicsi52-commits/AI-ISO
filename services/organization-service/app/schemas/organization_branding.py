"""Request/response schemas for ``/organizations/{id}/branding``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class OrganizationBrandingUpdateRequest(BaseModel):
    """Body of ``PUT /organizations/{id}/branding``."""

    logo_url: str | None = None
    dark_logo_url: str | None = None
    favicon_url: str | None = None
    primary_color: str | None = None
    secondary_color: str | None = None
    theme: str = "light"
    email_templates: dict[str, Any] = Field(default_factory=dict)
    login_screen_branding: dict[str, Any] = Field(default_factory=dict)
    dashboard_branding: dict[str, Any] = Field(default_factory=dict)


class OrganizationBrandingResponse(BaseModel):
    """One organization's branding, in full."""

    id: UUID
    organization_id: UUID
    logo_url: str | None
    dark_logo_url: str | None
    favicon_url: str | None
    primary_color: str | None
    secondary_color: str | None
    theme: str
    email_templates: dict[str, Any]
    login_screen_branding: dict[str, Any]
    dashboard_branding: dict[str, Any]
    created_at: datetime
    updated_at: datetime


__all__ = ["OrganizationBrandingResponse", "OrganizationBrandingUpdateRequest"]
