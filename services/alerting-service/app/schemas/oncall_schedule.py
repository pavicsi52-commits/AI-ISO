"""Request/response schemas for ``/oncall-schedules``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import OnCallRotationType


class OnCallScheduleCreateRequest(BaseModel):
    """Body of ``POST /oncall-schedules``."""

    organization_id: UUID
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    rotation_type: OnCallRotationType
    timezone: str = Field(default="UTC", max_length=64)
    participants: list[str] = Field(default_factory=list)
    overrides: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Temporary replacements beating the computed rotation, each "
            "{'user_id': ..., 'starts_at': ISO-8601, 'ends_at': ISO-8601}."
        ),
    )
    holiday_calendar: list[str] = Field(
        default_factory=list,
        description="ISO-8601 dates (YYYY-MM-DD) on which nobody is on call.",
    )
    enabled: bool = True


class OnCallScheduleResponse(BaseModel):
    """One on-call rotation schedule."""

    id: UUID
    organization_id: UUID
    project_id: UUID | None
    name: str
    rotation_type: OnCallRotationType
    timezone: str
    participants: list[str]
    overrides: list[dict[str, Any]]
    holiday_calendar: list[str]
    enabled: bool


class OnCallCurrentResponse(BaseModel):
    """Who is on call for a schedule right now."""

    schedule_id: UUID
    user_id: str | None


__all__ = [
    "OnCallCurrentResponse",
    "OnCallScheduleCreateRequest",
    "OnCallScheduleResponse",
]
