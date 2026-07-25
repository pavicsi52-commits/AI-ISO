"""Request/response schemas for ``/configurations/{id}/versions``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ConfigurationVersionCreateRequest(BaseModel):
    """Body of ``POST /configurations/{id}/versions`` -- a manual snapshot."""

    branch: str = Field(default="main", min_length=1, max_length=128)
    content: dict[str, Any] = Field(default_factory=dict)
    change_summary: str | None = Field(default=None, max_length=2048)


class ConfigurationVersionResponse(BaseModel):
    """One immutable snapshot of a profile's full desired state."""

    id: UUID
    profile_id: UUID
    version_number: str
    branch: str
    content: dict[str, Any]
    change_summary: str | None
    changed_by: UUID | None
    approved_by: UUID | None
    approved_at: datetime | None
    created_at: datetime


__all__ = ["ConfigurationVersionCreateRequest", "ConfigurationVersionResponse"]
