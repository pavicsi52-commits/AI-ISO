"""Request/response schemas for ``/organizations``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import OrganizationStatus


class OrganizationCreateRequest(BaseModel):
    """Body of ``POST /organizations``."""

    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=128)
    display_name: str | None = None
    short_name: str | None = None
    description: str | None = None
    primary_domain: str | None = None
    primary_contact_email: str | None = None
    website: str | None = None
    industry: str | None = None
    timezone: str = "UTC"
    language: str = "en"
    country: str | None = None
    currency: str = "USD"
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrganizationUpdateRequest(BaseModel):
    """Body of ``PUT /organizations/{id}``."""

    name: str = Field(min_length=1, max_length=255)
    display_name: str | None = None
    short_name: str | None = None
    description: str | None = None
    status: OrganizationStatus = OrganizationStatus.ACTIVE
    primary_domain: str | None = None
    primary_contact_email: str | None = None
    logo_url: str | None = None
    website: str | None = None
    industry: str | None = None
    timezone: str = "UTC"
    language: str = "en"
    country: str | None = None
    currency: str = "USD"
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrganizationResponse(BaseModel):
    """One organization, in full."""

    id: UUID
    name: str
    display_name: str | None
    short_name: str | None
    slug: str
    description: str | None
    status: OrganizationStatus
    primary_domain: str | None
    primary_contact_email: str | None
    logo_url: str | None
    website: str | None
    industry: str | None
    timezone: str
    language: str
    country: str | None
    currency: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


__all__ = ["OrganizationCreateRequest", "OrganizationResponse", "OrganizationUpdateRequest"]
