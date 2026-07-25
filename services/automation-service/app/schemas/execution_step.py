"""Response schema for one automation execution's own steps."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import ExecutionStepStatus


class AutomationExecutionStepResponse(BaseModel):
    """One ordered step within an automation execution."""

    id: UUID
    execution_id: UUID
    step_index: int
    name: str
    status: ExecutionStepStatus
    target_id: UUID | None
    started_at: datetime | None
    completed_at: datetime | None
    output: dict[str, Any] | None
    error_message: str | None


__all__ = ["AutomationExecutionStepResponse"]
