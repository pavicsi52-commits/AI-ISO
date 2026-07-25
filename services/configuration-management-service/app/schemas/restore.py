"""Request/response schemas for ``POST /configurations/{id}/restore``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import RestoreStatus, RestoreType


class ConfigurationRestoreCreateRequest(BaseModel):
    """Body of ``POST /configurations/{id}/restore``."""

    backup_id: UUID
    restore_type: RestoreType = RestoreType.PROFILE
    preview_only: bool = False
    requested_by: UUID | None = None


class ConfigurationRestoreJobResponse(BaseModel):
    """One restore operation from a backup back onto a profile."""

    id: UUID
    backup_id: UUID
    profile_id: UUID
    restore_type: RestoreType
    status: RestoreStatus
    preview_only: bool
    requested_by: UUID | None
    completed_at: datetime | None


__all__ = ["ConfigurationRestoreCreateRequest", "ConfigurationRestoreJobResponse"]
