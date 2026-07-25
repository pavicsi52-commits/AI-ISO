"""Request/response schemas for configuration-profile-to-asset assignments."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import ConfigurationAssignmentStatus


class ConfigurationAssignmentCreateRequest(BaseModel):
    """Body of ``POST /configurations/{id}/assignments``."""

    managed_asset_id: UUID


class ConfigurationAssignmentResponse(BaseModel):
    """One managed asset's assignment to a configuration profile."""

    id: UUID
    profile_id: UUID
    managed_asset_id: UUID
    status: ConfigurationAssignmentStatus
    assigned_by: UUID | None
    assigned_at: datetime


__all__ = ["ConfigurationAssignmentCreateRequest", "ConfigurationAssignmentResponse"]
