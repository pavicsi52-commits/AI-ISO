"""Request/response schemas for ``/organizations/{id}/quotas``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class OrganizationQuotaUpdateRequest(BaseModel):
    """Body of ``PUT /organizations/{id}/quotas``."""

    max_users: int = Field(default=10, ge=0)
    max_projects: int = Field(default=5, ge=0)
    max_assets: int = Field(default=1000, ge=0)
    max_storage_gb: int = Field(default=50, ge=0)
    max_workflows: int = Field(default=20, ge=0)
    max_automation_jobs: int = Field(default=50, ge=0)
    max_connectors: int = Field(default=10, ge=0)
    max_api_calls_per_day: int = Field(default=10_000, ge=0)
    max_ai_requests_per_day: int = Field(default=1_000, ge=0)
    max_plugins: int = Field(default=10, ge=0)


class OrganizationQuotaResponse(BaseModel):
    """One organization's quotas, in full."""

    id: UUID
    organization_id: UUID
    max_users: int
    max_projects: int
    max_assets: int
    max_storage_gb: int
    max_workflows: int
    max_automation_jobs: int
    max_connectors: int
    max_api_calls_per_day: int
    max_ai_requests_per_day: int
    max_plugins: int
    created_at: datetime
    updated_at: datetime


__all__ = ["OrganizationQuotaResponse", "OrganizationQuotaUpdateRequest"]
