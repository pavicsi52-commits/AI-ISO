"""Request/response schemas for ``POST /configurations/{id}/rollback``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import RollbackStatus, RollbackType


class ConfigurationRollbackCreateRequest(BaseModel):
    """Body of ``POST /configurations/{id}/rollback``."""

    to_version_id: UUID
    rollback_type: RollbackType = RollbackType.VERSION
    requested_by: UUID | None = None
    reason: str | None = Field(default=None, max_length=1024)


class ConfigurationRollbackDecisionRequest(BaseModel):
    """Body of ``PATCH /configurations/rollbacks/{id}`` -- approve/complete a rollback."""

    status: RollbackStatus
    approved_by: UUID | None = None


class ConfigurationRollbackResponse(BaseModel):
    """One rollback operation from a profile's current version to a prior one."""

    id: UUID
    profile_id: UUID
    from_version_id: UUID | None
    to_version_id: UUID
    rollback_type: RollbackType
    status: RollbackStatus
    requested_by: UUID | None
    approved_by: UUID | None
    completed_at: datetime | None
    reason: str | None


__all__ = [
    "ConfigurationRollbackCreateRequest",
    "ConfigurationRollbackDecisionRequest",
    "ConfigurationRollbackResponse",
]
