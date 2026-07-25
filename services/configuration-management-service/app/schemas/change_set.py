"""Request/response schemas for grouped configuration change sets."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ChangeSetStatus


class ConfigurationChangeSetCreateRequest(BaseModel):
    """Body of ``POST /configurations/{id}/change-sets``."""

    changes: list[dict[str, Any]] = Field(default_factory=list)


class ConfigurationChangeSetResponse(BaseModel):
    """One grouped set of field-level changes to a configuration profile."""

    id: UUID
    profile_id: UUID
    status: ChangeSetStatus
    changes: list[dict[str, Any]]
    applied_at: datetime | None
    created_by: UUID | None
    created_at: datetime


__all__ = ["ConfigurationChangeSetCreateRequest", "ConfigurationChangeSetResponse"]
