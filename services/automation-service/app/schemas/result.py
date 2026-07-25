"""Response schema for an automation execution's own final result summary."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AutomationResultResponse(BaseModel):
    """One final outcome summary for a completed automation execution."""

    id: UUID
    execution_id: UUID
    success: bool
    summary: str | None
    metrics: dict[str, Any]
    completed_at: datetime


__all__ = ["AutomationResultResponse"]
