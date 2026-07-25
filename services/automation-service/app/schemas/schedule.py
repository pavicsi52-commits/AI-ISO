"""Request/response schemas for automation job schedules."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AutomationScheduleCreateRequest(BaseModel):
    """Body of ``POST /automation/jobs/{id}/schedules``."""

    cron_expression: str = Field(min_length=1, max_length=128)
    enabled: bool = True


class AutomationScheduleResponse(BaseModel):
    """One recurring cron schedule for an automation job."""

    id: UUID
    job_id: UUID
    cron_expression: str
    enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None


__all__ = ["AutomationScheduleCreateRequest", "AutomationScheduleResponse"]
