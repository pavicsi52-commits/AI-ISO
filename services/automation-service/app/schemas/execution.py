"""Request/response schemas for ``/automation/executions`` and
``POST /automation/jobs/{id}/execute``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.enums import ExecutionMode, ExecutionStatus


class AutomationExecutionRequest(BaseModel):
    """Body of ``POST /automation/jobs/{id}/execute``."""

    target_ids: list[UUID] = Field(default_factory=list)
    variables: dict[str, Any] = Field(default_factory=dict)
    execution_mode: ExecutionMode = ExecutionMode.IMMEDIATE
    timeout_seconds: int | None = Field(default=None, ge=1)


class AutomationExecutionResponse(BaseModel):
    """One execution run of an automation job."""

    id: UUID
    organization_id: UUID
    job_id: UUID
    execution_plan_id: UUID | None
    status: ExecutionStatus
    execution_mode: ExecutionMode
    triggered_by: UUID | None
    variables: dict[str, Any]
    started_at: datetime | None
    completed_at: datetime | None
    timeout_seconds: int | None
    error_message: str | None
    created_at: datetime


__all__ = ["AutomationExecutionRequest", "AutomationExecutionResponse"]
