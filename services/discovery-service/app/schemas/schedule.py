"""Request/response schemas for ``/discovery/schedules``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ScheduleType


class DiscoveryScheduleCreateRequest(BaseModel):
    """Body of ``POST /discovery/schedules``."""

    organization_id: UUID
    profile_id: UUID
    name: str = Field(min_length=1, max_length=255)
    schedule_type: ScheduleType = ScheduleType.RECURRING
    cron_expression: str | None = None
    interval_seconds: int | None = Field(default=None, ge=1)
    next_run_at: datetime | None = None
    maintenance_window: dict[str, Any] = Field(default_factory=dict)
    retry_policy: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=5, ge=0, le=10)
    concurrency_limit: int = Field(default=1, ge=1)


class DiscoveryScheduleUpdateRequest(BaseModel):
    """Body of ``PUT /discovery/schedules/{id}``."""

    name: str = Field(min_length=1, max_length=255)
    schedule_type: ScheduleType = ScheduleType.RECURRING
    cron_expression: str | None = None
    interval_seconds: int | None = Field(default=None, ge=1)
    next_run_at: datetime | None = None
    is_enabled: bool = True
    maintenance_window: dict[str, Any] = Field(default_factory=dict)
    retry_policy: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=5, ge=0, le=10)
    concurrency_limit: int = Field(default=1, ge=1)


class DiscoveryScheduleResponse(BaseModel):
    """One discovery schedule."""

    id: UUID
    organization_id: UUID
    profile_id: UUID
    name: str
    schedule_type: ScheduleType
    cron_expression: str | None
    interval_seconds: int | None
    next_run_at: datetime | None
    last_run_at: datetime | None
    is_enabled: bool
    priority: int
    concurrency_limit: int


__all__ = [
    "DiscoveryScheduleCreateRequest",
    "DiscoveryScheduleResponse",
    "DiscoveryScheduleUpdateRequest",
]
