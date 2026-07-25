"""Response schema for ``GET /automation/executions/{id}/logs``."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models.enums import LogLevel


class AutomationExecutionLogResponse(BaseModel):
    """One structured log line captured during an automation execution."""

    id: UUID
    execution_id: UUID
    step_id: UUID | None
    level: LogLevel
    message: str
    metadata: dict[str, Any]
    logged_at: datetime


__all__ = ["AutomationExecutionLogResponse"]
